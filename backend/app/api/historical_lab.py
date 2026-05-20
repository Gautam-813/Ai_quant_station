from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import json
import logging
import pandas as pd
import asyncio
import re
from pydantic import BaseModel, Field

from app.core.historical_loader import load_data, add_indicators, get_available_years, AVAILABLE_SYMBOLS
from app.core.backtest_engine import BacktestEngine, DeepAnalysisEngine
from app.core.database import get_db, AsyncSessionLocal
from app.core.security import get_current_user
from app.models.historical_lab import HistoricalBacktest
from app.core.config import settings
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/historical-lab", tags=["Historical Lab"])

# ─────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────

class LabRequest(BaseModel):
    mode: str                    # "backtest" or "analysis"
    symbol: str                  # e.g. "XAUUSD"
    start_date: str              # e.g. "2010-01-01"
    end_date: str                # e.g. "2025-12-31"
    timeframe: str = "1T"        # "1T", "5T", "1H"
    prompt: Optional[str] = ""   # User's strategy/analysis description
    # Backtest-only fields
    initial_capital: float = 10000.0
    leverage: float = 100.0
    include_spread: bool = False
    include_commission: bool = False
    provider: Optional[str] = "nvidia"
    model: Optional[str] = "qwen/qwen3.5-122b-a10b"


class LabResponse(BaseModel):
    id: int
    mode: str
    symbol: str
    status: str
    equity_curve: Optional[list] = None
    metrics: Optional[dict] = None
    analysis: Optional[dict] = None
    ai_report: Optional[str] = Field(default="")
    chat_history: List[dict] = []


class ChatMessageRequest(BaseModel):
    backtest_id: int
    message: str
    provider: Optional[str] = "nvidia"
    model: Optional[str] = "qwen/qwen3.5-122b-a10b"


# ─────────────────────────────────────────────
# Utility & AI Helpers
# ─────────────────────────────────────────────

async def _generate_signals_from_prompt(df: pd.DataFrame, prompt: str, symbol: str, provider: str = "nvidia", model: str = "qwen/qwen3.5-122b-a10b"):
    """Use AI to generate a signal column (1, -1, 0) based on natural language strategy."""
    if not prompt:
        df["signal"] = 0
        return df
        
    system_prompt = f"""You are a Strategy Developer. Given a dataset 'df' for {symbol} and a strategy description, write Python code to:
1. Calculate necessary indicators.
2. Create a 'signal' column where 1=BUY, -1=SELL, 0=NONE.
3. Ensure the 'signal' column is added to 'df'.

Strategy: {prompt}

ONLY output the Python code block. No explanation."""

    try:
        client = await _get_ai_client(provider)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.1,
            timeout=30
        )
        code = response.choices[0].message.content or ""
        python_match = re.search(r"```python\s*(.*?)(?:```|$)", code, re.S)
        if python_match:
            code_clean = python_match.group(1)
            # Execute in a safe environment
            from .execute import run_python_code
            res = await run_python_code(code_clean, df.to_dict('records'), symbol)
            
            if res.get("success") and res.get("modified_data"):
                # Convert modified records back to DataFrame
                df_mod = pd.DataFrame(res["modified_data"])
                if "signal" in df_mod.columns:
                    # Ensure same index and merge signal
                    df["signal"] = df_mod["signal"].values
                    logger.info(f"Successfully integrated AI signals for {symbol}")
                else:
                    logger.warning("AI code executed but no 'signal' column found.")
            else:
                logger.error(f"Signal code execution failed: {res.get('error')}")
    except Exception as e:
        logger.error(f"Signal generation error: {e}")
    
    return df

async def _get_ai_client(provider: str = "nvidia"):
    from ..core.providers import PROVIDERS, get_api_key, get_base_url
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    api_key = get_api_key(provider, settings)
    if not api_key:
        raise ValueError(f"No API key configured for {provider}")
    return AsyncOpenAI(base_url=get_base_url(provider), api_key=api_key)

def _generate_initial_report(mode: str, symbol: str, start: str, end: str,
                             metrics: Optional[dict], analysis: Optional[dict]) -> str:
    if mode == "backtest" and metrics:
        return (
            f"**Strategy Analysis ({symbol} | {start} → {end})**\n\n"
            f"**Total Return:** {metrics.get('total_return_pct', 0):+.2f}% | **Sharpe:** {metrics.get('sharpe_ratio', 0):.2f}\n"
            f"**Win Rate:** {metrics.get('win_rate_pct', 0):.1f}% | **Max Drawdown:** {metrics.get('max_drawdown_pct', 0):.1f}%\n\n"
            f"What specific details would you like to discuss?"
        )
    elif mode == "analysis" and analysis:
        stats = analysis.get("stats", {})
        return (
            f"**Deep Market Analysis ({symbol})**\n\n"
            f"Analyzed {stats.get('total_bars', 0):,} bars. How can I help you interpret these patterns?"
        )
    return "Analysis complete."


# ─────────────────────────────────────────────
# Background Task Engine
# ─────────────────────────────────────────────

async def run_backtest_task(backtest_id: int, request_data: dict):
    """Heavy mathematical processing runs here in the background."""
    async with AsyncSessionLocal() as db:
        try:
            # 1. Update status to 'running'
            result = await db.execute(select(HistoricalBacktest).where(HistoricalBacktest.id == backtest_id))
            record = result.scalar_one_or_none()
            if not record: return
            
            record.status = "running"
            await db.commit()
            
            # 2. Execute Logic
            df = load_data(record.symbol, record.start_date.strftime('%Y-%m-%d'), record.end_date.strftime('%Y-%m-%d'), record.timeframe)
            if df is None or df.empty:
                raise ValueError("No data found for the selected range.")
                
            df = add_indicators(df)
            
            equity_curve = None
            metrics = None
            analysis = None
            
            if record.mode == "backtest":
                # AI-driven strategy translation
                df = await _generate_signals_from_prompt(df, record.prompt or "", record.symbol)
                
                engine = BacktestEngine(
                    initial_capital=record.initial_capital,
                    leverage=record.leverage,
                    spread_pips=3.0 if record.include_spread else 0.0,
                    commission_per_lot=7.0 if record.include_commission else 0.0
                )
                res = engine.run(df)
                if res:
                    equity_curve = res["equity_curve"]
                    metrics = res["metrics"]
            else:
                engine = DeepAnalysisEngine()
                analysis = engine.run(df)
                
            # 3. Generate initial AI response
            report = _generate_initial_report(record.mode, record.symbol, record.start_date.isoformat(), record.end_date.isoformat(), metrics, analysis)
            
            # 4. Update Record
            record.metrics = metrics
            record.equity_curve = equity_curve
            record.analysis_data = analysis
            record.chat_history = [{"role": "assistant", "content": report}]
            record.status = "completed"
            
            await db.commit()
            logger.info(f"Background Backtest {backtest_id} completed successfully.")
            
        except Exception as e:
            logger.error(f"Background Backtest Error: {e}")
            # Ensure we update the record to 'failed' so the UI stops loading
            result = await db.execute(select(HistoricalBacktest).where(HistoricalBacktest.id == backtest_id))
            record = result.scalar_one_or_none()
            if record:
                record.status = "failed"
                record.error_message = str(e)
                await db.commit()


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post("/run")
async def run_lab(
    request: LabRequest, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if request.symbol not in AVAILABLE_SYMBOLS:
        raise HTTPException(status_code=400, detail="Invalid symbol.")
    
    # 1. Create a "Pending" record immediately
    backtest_record = HistoricalBacktest(
        user_id=current_user["id"],
        symbol=request.symbol,
        start_date=pd.to_datetime(request.start_date),
        end_date=pd.to_datetime(request.end_date),
        timeframe=request.timeframe,
        mode=request.mode,
        prompt=request.prompt,
        initial_capital=request.initial_capital,
        leverage=request.leverage,
        include_spread=request.include_spread,
        include_commission=request.include_commission,
        status="pending"
    )
    
    db.add(backtest_record)
    await db.commit()
    await db.refresh(backtest_record)
    
    background_tasks.add_task(run_backtest_task, backtest_record.id, request.model_dump())
    
    return {"id": backtest_record.id, "status": "pending"}


@router.get("/status/{backtest_id}", response_model=LabResponse)
async def get_status(
    backtest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    result = await db.execute(
        select(HistoricalBacktest).where(
            HistoricalBacktest.id == backtest_id,
            HistoricalBacktest.user_id == current_user["id"]
        )
    )
    record = result.scalar_one_or_none()
    
    if not record:
        raise HTTPException(status_code=404, detail="Backtest not found.")
        
    return LabResponse(
        id=record.id,
        mode=record.mode,
        symbol=record.symbol,
        status=record.status,
        equity_curve=record.equity_curve,
        metrics=record.metrics,
        analysis=record.analysis_data,
        ai_report=str(record.chat_history[-1].get("content", "") or "") if record.chat_history else "",
        chat_history=record.chat_history
    )


@router.post("/chat", response_model=LabResponse)
async def chat_followup(
    request: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    result = await db.execute(
        select(HistoricalBacktest).where(
            HistoricalBacktest.id == request.backtest_id,
            HistoricalBacktest.user_id == current_user["id"]
        )
    )
    record = result.scalar_one_or_none()
    
    if not record or record.status != "completed":
        raise HTTPException(status_code=400, detail="Backtest not ready for chat.")
    
    # Build Context
    context = f"Context: Market {record.symbol} from {record.start_date.date()} to {record.end_date.date()} on {record.timeframe} timeframe. "
    if record.mode == "backtest":
        context += f"Backtest Results: {record.metrics.get('total_return_pct')}% total return, {record.metrics.get('sharpe_ratio')} Sharpe, {record.metrics.get('win_rate_pct')}% win rate, {record.metrics.get('num_trades')} trades."
    else:
        stats = record.analysis_data.get("stats", {})
        context += f"Analysis Results: {stats.get('total_bars', 0)} bars analyzed. "
        context += f"Mean Daily Return: {stats.get('mean_return_pct')}% (Std: {stats.get('std_return_pct')}%). "
        context += f"Avg ATR (14): {stats.get('avg_atr_14', 'N/A')}."
        
    system_prompt = f"""You are a Lead Quant Analyst in the Research Vault.
{context}

You have access to the COMPLETE historical dataset in a variable called 'df'.
TECHNICAL GUIDELINES:
1. Technical indicators (ATR, RSI, etc.) produce 'NaN' values for the first N periods. ALWAYS use '.dropna()' or handle these NaNs before performing calculations like '.idxmax()', '.mean()', or '.iloc[-1]'.
2. If the user asks for a calculation (like Max ATR), compute it on the server and use 'print()' to show the final result.
3. Use 'show_chart(data, title)' or 'show_table(df, title)' for visualizations.
4. The system automatically caps tables at 50 rows, so focus on summary statistics for large datasets.
5. The 'df' variable contains: open, high, low, close, volume, datetime.

Be precise, professional, and mathematically rigorous."""

    messages = [
        {"role": "system", "content": system_prompt},
    ]
    for msg in record.chat_history: messages.append(msg)
    user_msg = {"role": "user", "content": request.message}
    messages.append(user_msg)
    
    last_error = ""
    for attempt in range(2):
        try:
            client = await _get_ai_client(request.provider)
            response = await client.chat.completions.create(
                model=request.model,
                messages=messages,
                temperature=0.2,
                max_tokens=4000,
                timeout=30
            )
            
            msg_obj = response.choices[0].message
            ai_content = getattr(msg_obj, 'content', None) or getattr(msg_obj, 'reasoning_content', None) or ""
            
            if not ai_content:
                if attempt == 0: continue
                raise ValueError("Empty AI response")

            # --- Agentic Execution Loop with Self-Correction ---
            execution_results = None
            python_match = re.search(r"```python\s*(.*?)(?:```|$)", ai_content, re.S)
            
            if python_match:
                from .execute import run_python_code
                from ..core.historical_loader import load_data, add_indicators
                
                df = load_data(record.symbol, record.start_date.strftime('%Y-%m-%d'), record.end_date.strftime('%Y-%m-%d'), record.timeframe)
                if df is not None:
                    df = add_indicators(df)
                    code = python_match.group(1)
                    execution_results = await run_python_code(code, df.to_dict('records'), record.symbol)

                    # Self-correction: if code failed, ask AI to fix it
                    if not execution_results.get("success"):
                        logger.warning(f"Code execution failed: {execution_results.get('error')}. Attempting self-correction...")
                        try:
                            correction_messages = messages + [
                                {"role": "assistant", "content": ai_content},
                                {"role": "user", "content": f"The Python code you provided failed with: {execution_results.get('error')}. Please provide a FIXED version."}
                            ]
                            response = await client.chat.completions.create(
                                model=request.model,
                                messages=correction_messages,
                                temperature=0.1,
                                max_tokens=4000,
                                timeout=30
                            )
                            ai_content = response.choices[0].message.content or ""
                            new_match = re.search(r"```python\s*(.*?)(?:```|$)", ai_content, re.S)
                            if new_match:
                                execution_results = await run_python_code(new_match.group(1), df.to_dict('records'), record.symbol)
                        except Exception as ce:
                            logger.error(f"Self-correction failed: {ce}")

            # Build structured message
            ai_msg_data = {
                "role": "assistant", 
                "content": str(ai_content),
                "execution_output": execution_results.get("output") if execution_results else None,
                "execution_charts": execution_results.get("charts") if execution_results else None,
                "execution_tables": execution_results.get("tables") if execution_results else None,
            }
            
            # Recursive cleaner for JSON serialization safety
            def _clean_for_json(obj):
                from datetime import date, time, datetime
                import math
                if isinstance(obj, (datetime, pd.Timestamp)): return obj.isoformat()
                if isinstance(obj, (date, time)): return str(obj)
                if isinstance(obj, dict): return {k: _clean_for_json(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple)): return [_clean_for_json(i) for i in obj]
                if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)): return None
                return obj

            ai_msg_data = _clean_for_json(ai_msg_data)
            
            new_history = list(record.chat_history)
            new_history.extend([user_msg, ai_msg_data])
            record.chat_history = new_history
            await db.commit()
            await db.refresh(record)
            
            return await get_status(record.id, db, current_user)
            
        except Exception as e:
            await db.rollback() # Recover the session
            last_error = str(e)
            logger.error(f"Chat error: {e}")
            if attempt < 1:
                await asyncio.sleep(1)
            else:
                raise HTTPException(status_code=500, detail=f"AI service error after retries: {last_error}")

@router.get("/available-symbols")
async def get_symbols():
    return {"symbols": AVAILABLE_SYMBOLS}

@router.get("/available-years/{symbol}")
async def get_years(symbol: str):
    years = get_available_years(symbol)
    return {"symbol": symbol, "years": years, "from": min(years) if years else None, "to": max(years) if years else None}
