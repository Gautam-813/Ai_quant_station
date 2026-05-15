from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import json
import logging
import pandas as pd

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


class LabResponse(BaseModel):
    id: int
    mode: str
    symbol: str
    status: str
    equity_curve: Optional[list] = None
    metrics: Optional[dict] = None
    analysis: Optional[dict] = None
    ai_report: str = ""
    chat_history: List[dict] = []


class ChatMessageRequest(BaseModel):
    backtest_id: int
    message: str


# ─────────────────────────────────────────────
# Utility & AI Helpers
# ─────────────────────────────────────────────

def _apply_strategy_from_prompt(df, prompt: str):
    prompt_lower = prompt.lower()
    df["signal"] = 0
    if "rsi" in prompt_lower:
        oversold, overbought = 30, 70
        if "rsi_14" in df.columns:
            df.loc[df["rsi_14"] < oversold, "signal"] = 1
            df.loc[df["rsi_14"] > overbought, "signal"] = -1
    elif "ema" in prompt_lower or "crossover" in prompt_lower:
        if "ema_9" in df.columns and "ema_21" in df.columns:
            df.loc[df["ema_9"] > df["ema_21"], "signal"] = 1
            df.loc[df["ema_9"] < df["ema_21"], "signal"] = -1
    elif "macd" in prompt_lower:
        if "macd" in df.columns and "macd_signal" in df.columns:
            df.loc[df["macd"] > df["macd_signal"], "signal"] = 1
            df.loc[df["macd"] < df["macd_signal"], "signal"] = -1
    elif "bollinger" in prompt_lower or "band" in prompt_lower:
        if "bb_upper" in df.columns and "bb_lower" in df.columns:
            df.loc[df["close"] < df["bb_lower"], "signal"] = 1
            df.loc[df["close"] > df["bb_upper"], "signal"] = -1
    return df

async def _get_ai_client():
    api_key = settings.NVIDIA_API_KEY
    if not api_key.startswith("nvapi-"): api_key = f"nvapi-{api_key}"
    return AsyncOpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)

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
                df = _apply_strategy_from_prompt(df, record.prompt or "")
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
    
    # 2. Trigger background task
    background_tasks.add_task(run_backtest_task, backtest_record.id, request.dict())
    
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
        ai_report=record.chat_history[-1]["content"] if record.chat_history else "",
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
    context = f"Backtest on {record.symbol} ({record.start_date.date()} to {record.end_date.date()}). "
    if record.mode == "backtest":
        context += f"Metrics: {record.metrics.get('total_return_pct')}% return, {record.metrics.get('sharpe_ratio')} Sharpe."
        
    messages = [
        {"role": "system", "content": f"You are a Quant Analyst. {context} Discuss the results with the user."},
    ]
    for msg in record.chat_history[-5:]: messages.append(msg)
    user_msg = {"role": "user", "content": request.message}
    messages.append(user_msg)
    
    try:
        client = await _get_ai_client()
        response = await client.chat.completions.create(
            model="qwen/qwen3.5-122b-a10b",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        ai_msg = {"role": "assistant", "content": response.choices[0].message.content}
        
        new_history = list(record.chat_history)
        new_history.extend([user_msg, ai_msg])
        record.chat_history = new_history
        await db.commit()
        await db.refresh(record)
        
        return await get_status(record.id, db, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/available-symbols")
async def get_symbols():
    return {"symbols": AVAILABLE_SYMBOLS}

@router.get("/available-years/{symbol}")
async def get_years(symbol: str):
    years = get_available_years(symbol)
    return {"symbol": symbol, "years": years, "from": min(years) if years else None, "to": max(years) if years else None}
