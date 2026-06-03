from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
import json
import logging
import pandas as pd
import numpy as np
import asyncio
import re
from pydantic import BaseModel, Field

from app.core.historical_loader import load_data, add_indicators, get_available_years, AVAILABLE_SYMBOLS
from app.core.backtest_engine import BacktestEngine, DeepAnalysisEngine
from app.core.database import get_db, AsyncSessionLocal
from app.core.security import get_current_user
from app.models.historical_lab import HistoricalBacktest
from app.core.config import settings
from app.core.utils import sanitize_for_json as _clean_for_json
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/historical-lab", tags=["Historical Lab"])


def _capture_raw_response(response) -> dict | None:
    try:
        return response.model_dump(mode='json')
    except Exception:
        try:
            return response.dict()
        except Exception:
            return None

# ── DataFrame cache for chat follow-ups ────────────────────────────────────
# Cache key: backtest_id, Value: (timestamp, DataFrame with indicators)
# TTL: 5 minutes after last access
_df_cache: dict[int, tuple[float, pd.DataFrame]] = {}
_DF_CACHE_TTL = 300  # seconds

TF_MAPPING = {
    "M1": "1T", "M5": "5T", "M15": "15T", "M30": "30T",
    "H1": "1H", "H2": "2H", "H4": "4H",
    "D1": "1D", "W1": "1W",
}

_NL_TF_PATTERNS = [
    (r'\b1[-\s]?(?:m|min(?:ute)?s?)\b', "1T"),
    (r'\b5[-\s]?(?:m|min(?:ute)?s?)\b', "5T"),
    (r'\b15[-\s]?(?:m|min(?:ute)?s?)\b', "15T"),
    (r'\b30[-\s]?(?:m|min(?:ute)?s?)\b', "30T"),
    (r'\b1[-\s]?(?:h|hour(?:ly)?s?)\b|\bhourly\b', "1H"),
    (r'\b2[-\s]?(?:h|hour(?:s)?)\b', "2H"),
    (r'\b4[-\s]?(?:h|hour(?:s)?)\b|\bfour[-\s]?hour\b', "4H"),
    (r'\b1[-\s]?(?:d|day(?:s)?)\b|\bdaily\b', "1D"),
    (r'\b1[-\s]?(?:w|week(?:s)?)\b|\bweekly\b', "1W"),
]

def _extract_timeframes(prompt: str, primary_tf: str) -> list:
    """Extract timeframe references from a strategy prompt.

    Returns list of Pandas offset strings (e.g. ['5T', '15T', '1H']).
    Always includes the primary timeframe.
    """
    detected = {primary_tf}
    for label, offset in TF_MAPPING.items():
        if re.search(rf'\b{label}\b', prompt, re.IGNORECASE):
            detected.add(offset)
    for pattern, offset in _NL_TF_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            detected.add(offset)
    return sorted(detected, key=lambda x: _tf_sort_key(x))

def _tf_sort_key(tf: str) -> int:
    """Sort timeframes ascending by granularity (1T < 5T < 15T < 1H < 4H < 1D)."""
    u = tf[-1]
    v = int(tf[:-1])
    scale = {"T": 1, "H": 60, "D": 1440}.get(u, 999)
    return v * scale

def _load_multi_timeframe(symbol: str, start: str, end: str, timeframes: list) -> dict:
    """Load 1-minute data and resample to multiple timeframes with indicators.

    Returns dict: {"1H": df_h1_with_indicators, "15T": df_m15_with_indicators, ...}
    """
    df_1m = load_data(symbol, start, end, "1T")
    if df_1m is None:
        return {}
    # load_data resets the index; restore datetime index for resampling
    if "datetime" in df_1m.columns:
        df_1m = df_1m.set_index("datetime")
    if not isinstance(df_1m.index, pd.DatetimeIndex):
        logger.warning(f"Base data index is {type(df_1m.index).__name__}, converting")
        df_1m.index = pd.to_datetime(df_1m.index)

    result = {}
    for tf in timeframes:
        try:
            if tf == "1T":
                df_tf = df_1m.copy()
            else:
                df_tf = df_1m.resample(tf).agg({
                    "open": "first", "high": "max", "low": "min",
                    "close": "last", "volume": "sum", "timestamp": "first"
                }).dropna()
            if not isinstance(df_tf.index, pd.DatetimeIndex):
                df_tf.index = pd.to_datetime(df_tf.index)
            df_tf = add_indicators(df_tf)
            result[tf] = df_tf
        except Exception as e:
            logger.error(f"Failed to load timeframe {tf}: {e}")
            continue
    return result

def _merge_higher_tf(df_primary: pd.DataFrame, extra_dfs: dict, primary_tf: str) -> pd.DataFrame:
    """Merge higher-timeframe indicator columns into the primary dataframe with _<tf> suffix.

    Example: H1's rsi_14 column becomes rsi_14_1h in the M15 primary df.
    """
    if not isinstance(df_primary.index, pd.DatetimeIndex):
        df_primary = df_primary.copy()
        df_primary.index = pd.to_datetime(df_primary.index)
    df = df_primary.copy()
    for tf, df_extra in extra_dfs.items():
        if tf == primary_tf:
            continue
        if not isinstance(df_extra.index, pd.DatetimeIndex):
            continue
        suffix = f"_{tf.replace('T', 'min').replace('H', 'h').replace('D', 'd')}"
        indicator_cols = [c for c in df_extra.columns if c not in ('open', 'high', 'low', 'close', 'volume', 'timestamp')]
        for col in indicator_cols:
            df[f"{col}{suffix}"] = df_extra[col].reindex(df.index, method='ffill').bfill()
    return df


def _get_cached_df(backtest_id: int, symbol: str, start: str, end: str, timeframe: str) -> pd.DataFrame:
    """Return cached DataFrame if fresh, otherwise load and cache it."""
    import time as _time
    now = _time.monotonic()
    if backtest_id in _df_cache:
        ts, df = _df_cache[backtest_id]
        if now - ts < _DF_CACHE_TTL:
            return df
    df = load_data(symbol, start, end, timeframe)
    if df is not None:
        df = add_indicators(df)
        _df_cache[backtest_id] = (_time.monotonic(), df)
    return df


def _prune_df_cache():
    """Remove expired entries from the DataFrame cache."""
    import time as _time
    now = _time.monotonic()
    expired = [k for k, v in _df_cache.items() if now - v[0] > _DF_CACHE_TTL]
    for k in expired:
        _df_cache.pop(k, None)

# ─────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────

class LabRequest(BaseModel):
    mode: str                    # "backtest" or "analysis"
    symbol: str                  # e.g. "XAUUSD"
    start_date: str              # e.g. "2010-01-01"
    end_date: str                # e.g. "2025-12-31"
    timeframe: str = "1T"        # "1T", "5T", "1H"
    timeframes: Optional[List[str]] = None  # Auto-detected from prompt if not set
    prompt: Optional[str] = ""   # User's strategy/analysis description
    # Backtest-only fields
    initial_capital: float = 10000.0
    lot_size: float = 0.01
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
    trade_log: Optional[list] = None


class ChatMessageRequest(BaseModel):
    backtest_id: int
    message: str
    provider: Optional[str] = "nvidia"
    model: Optional[str] = "qwen/qwen3.5-122b-a10b"


# ─────────────────────────────────────────────
# Utility & AI Helpers
# ─────────────────────────────────────────────

async def _generate_signals_from_prompt(df: pd.DataFrame, prompt: str, symbol: str, provider: str = "nvidia", model: str = "qwen/qwen3.5-122b-a10b", user_id: int = 0):
    """Use AI to generate a signal column (1, -1, 0) based on natural language strategy.
    
    Returns (df_with_signals, generated_code)."""
    generated_code = ""
    if not prompt:
        df["signal"] = 0
        return df, generated_code

    # Build column description for the AI
    base_cols = ['open', 'high', 'low', 'close', 'volume', 'datetime']
    indicator_cols = sorted([c for c in df.columns if c not in base_cols and c != 'timestamp'])
    indicator_str = ", ".join(indicator_cols[:50])  # cap at 50 to avoid huge prompts
    extra_info = ""
    extra_tf_cols = [c for c in indicator_cols if c.count('_') > 1 and c.rsplit('_', 1)[1] in ('1h', '4h', '1d', '5min', '15min', '30min', '1w')]
    if extra_tf_cols:
        shown = extra_tf_cols[:10]
        extra_info = f"\nNOTE: Columns ending with _1h, _4h, _5min, _15min etc. are from higher timeframes merged into this df. For example, rsi_14_1h is the H1 RSI value."

    system_prompt = f"""You are a Strategy Developer. You MUST write Python code — NO text, NO explanations.

GIVEN:
- A pandas DataFrame `df` loaded in the sandbox with columns: {indicator_str}
- df already has a datetime index. Do NOT modify or recreate it.
- The 'ta' library is available. Use existing columns first; only calculate new ones if needed.{extra_info}

CRITICAL — NEVER do any of these:
- NEVER create or assign datetime, date, or time columns (df already has them)
- NEVER use string literals like '2020-01-01' or pd.date_range()
- NEVER use groupby, shift, rolling with date-offset strings
- NEVER use string operations on column names or values
- Use only numeric column values in calculations

YOUR TASK:
Write code that adds a 'signal' column to 'df' where:
  - 1 = BUY
  - -1 = SELL  
  - 0 = NO SIGNAL

If the strategy references concepts not in 'df' (e.g., session times, spread, position management rules), ADAPT the logic to use only what's available. For example, use ATR instead of ADX.

RULES:
- Use columns from df directly (e.g. df['rsi_14'], df['ema_9_1h']).
- Do NOT try to load files, call APIs, or reference undefined variables.
- Output ONLY ```python ... ``` with no text before or after.
- Outputting ANY text outside the code block will cause rejection.

Strategy: {prompt}

Write ONLY the code block now:"""

    try:
        client = await _get_ai_client(provider, user_id=user_id)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Generate strategy code for {symbol} using only the columns in df."}
        ]
        
        for attempt in range(2):
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.05 if attempt == 0 else 0.2,
                timeout=30
            )
            raw = response.choices[0].message.content or ""
            
            python_match = re.search(r"```python\s*(.*?)(?:```|$)", raw, re.S)
            if not python_match:
                logger.warning(f"Signal code attempt {attempt+1} had no code block. Retrying...")
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": "You MUST output Python code inside ```python ... ```. No text, no explanations. Only the code block."})
                continue
            
            code_clean = python_match.group(1)
            generated_code = code_clean
            from .execute import run_python_code
            res = await run_python_code(code_clean, symbol=symbol, inject_df=df.copy(), user_id=user_id)
            
            if res.get("success") and res.get("modified_data"):
                df_mod = pd.DataFrame(res["modified_data"])
                if "signal" in df_mod.columns:
                    df["signal"] = df_mod["signal"].values[:len(df)]
                    logger.info(f"Successfully integrated AI signals for {symbol}")
                    break
                else:
                    error_detail = "Signal column not found in output"
            else:
                error_detail = (res.get("error") or "Unknown error")[:500]
            
            logger.warning(f"Signal code attempt {attempt+1} failed: {error_detail}. Asking AI to fix...")
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"Your previous code failed with: {error_detail}. Fix the error and output ONLY valid Python code inside ```python ... ```."})
        
    except Exception as e:
        logger.error(f"Signal generation error: {e}")
    
    return df, generated_code

async def _get_ai_client(provider: str = "nvidia", user_id: int = 0):
    from ..core.providers import PROVIDERS, get_base_url, resolve_api_key
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    api_key = await resolve_api_key(provider, settings, user_id, AsyncSessionLocal)
    if not api_key:
        raise ValueError(f"No API key configured for {provider}")
    if provider == "nvidia" and not api_key.startswith("nvapi-"):
        api_key = f"nvapi-{api_key}"
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
        hourly = analysis.get("hourly_volatility", [])
        dow = analysis.get("day_of_week_volatility", [])
        peak_hour = max(hourly, key=lambda h: h["avg_range"]) if hourly else {}
        peak_day = max(dow, key=lambda d: d["avg_range"]) if dow else {}
        return (
            f"**Deep Market Analysis ({symbol})**\n\n"
            f"**Total Bars Analyzed:** {stats.get('total_bars', 0):,}\n"
            f"**Mean Daily Return:** {stats.get('mean_return_pct', 0):+.4f}% (Std: {stats.get('std_return_pct', 0):.4f}%)\n"
            f"**Average ATR (14):** {stats.get('avg_atr_14', 0):.2f}\n"
            f"**Best Day:** {stats.get('best_day', 'N/A')} | **Worst Day:** {stats.get('worst_day', 'N/A')}\n"
            f"**Peak Volatility Hour:** UTC {peak_hour.get('hour_utc', 'N/A')}h (range: {peak_hour.get('avg_range', 0):.2f})\n"
            f"**Peak Volatility Day:** {peak_day.get('day', 'N/A')} (range: {peak_day.get('avg_range', 0):.2f})\n\n"
            f"Charts are displayed above with hourly and day-of-week volatility breakdowns. "
            f"What specific aspect would you like to explore further?"
        )
    return "Analysis complete."


# ─────────────────────────────────────────────
# Background Task Engine
# ─────────────────────────────────────────────

async def run_backtest_task(backtest_id: int, request_data: dict, user_id: int = 0):
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
            prompt_text = record.prompt or ""
            if record.timeframes:
                tfs = record.timeframes
            else:
                tfs = _extract_timeframes(prompt_text, record.timeframe)
            
            tf_data = _load_multi_timeframe(record.symbol, record.start_date.strftime('%Y-%m-%d'), record.end_date.strftime('%Y-%m-%d'), tfs)
            primary_key = record.timeframe
            df = tf_data.get(primary_key)
            if df is None or df.empty:
                raise ValueError("No data found for the selected range.")
            
            # Merge higher-TF indicators into primary df
            df = _merge_higher_tf(df, tf_data, primary_key)
            
            # Seed the DataFrame cache so chat follow-ups don't reload from disk
            import time as _time
            _df_cache[backtest_id] = (_time.monotonic(), df.copy())
            
            equity_curve = None
            metrics = None
            analysis = None
            trade_log = None
            
            if record.mode == "backtest":
                # AI-driven strategy translation
                df, generated_code = await _generate_signals_from_prompt(
                    df, record.prompt or "", record.symbol,
                    provider=record.provider or "nvidia",
                    model=record.model or "qwen/qwen3.5-122b-a10b",
                    user_id=user_id
                )
                record.generated_code = generated_code
            
            # Engines expect 'datetime' as a column, not DatetimeIndex
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index()
            
            if record.mode == "backtest":
                engine = BacktestEngine(
                    initial_capital=record.initial_capital,
                    lot_size=record.lot_size or 0.01,
                    spread_pips=3.0 if record.include_spread else 0.0,
                    commission_per_lot=7.0 if record.include_commission else 0.0
                )
                res = engine.run(df)
                if res:
                    equity_curve = res["equity_curve"]
                    metrics = res["metrics"]
                    trade_log = res.get("trade_log")
            else:
                engine = DeepAnalysisEngine()
                analysis = engine.run(df)
                
            # 3. Generate initial AI response
            report = _generate_initial_report(record.mode, record.symbol, record.start_date.isoformat(), record.end_date.isoformat(), metrics, analysis)
            
            # 4. Update Record
            record.metrics = metrics
            record.equity_curve = equity_curve
            record.analysis_data = analysis
            record.trade_log = trade_log
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
    
    # Auto-detect timeframes from prompt if not explicitly set
    if request.timeframes:
        detected_tfs = request.timeframes
    else:
        detected_tfs = _extract_timeframes(request.prompt or "", request.timeframe)

    # 1. Create a "Pending" record immediately
    backtest_record = HistoricalBacktest(
        user_id=current_user["id"],
        symbol=request.symbol,
        start_date=datetime.strptime(request.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc),
        end_date=datetime.strptime(request.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc),
        timeframe=request.timeframe,
        timeframes=detected_tfs,
        mode=request.mode,
        prompt=request.prompt,
        provider=request.provider or "nvidia",
        model=request.model or "qwen/qwen3.5-122b-a10b",
        initial_capital=request.initial_capital,
        lot_size=request.lot_size,
        include_spread=request.include_spread,
        include_commission=request.include_commission,
        status="pending"
    )
    
    db.add(backtest_record)
    await db.commit()
    await db.refresh(backtest_record)
    
    background_tasks.add_task(run_backtest_task, backtest_record.id, request.model_dump(), current_user["id"])
    
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
        chat_history=record.chat_history,
        trade_log=record.trade_log,
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
    
    # Prune stale cache entries before using cache
    _prune_df_cache()
    
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
            client = await _get_ai_client(request.provider, user_id=current_user["id"])
            response = await client.chat.completions.create(
                model=request.model,
                messages=messages,
                temperature=0.2,
                max_tokens=32768,
                timeout=30
            )
            
            msg_obj = response.choices[0].message
            ai_content = msg_obj.content or ""
            reasoning_text = msg_obj.reasoning_content if hasattr(msg_obj, 'reasoning_content') and msg_obj.reasoning_content else None
            full_raw_response = _capture_raw_response(response)
            
            # Fallback: use reasoning_content if content is empty
            if not ai_content and reasoning_text:
                ai_content = reasoning_text
            
            if not ai_content and not reasoning_text:
                if attempt == 0: continue
                raise ValueError("Empty AI response")

            # --- Agentic Execution Loop with Multi-Attempt Self-Correction ---
            execution_results = None
            MAX_EXEC_RETRIES = 2
            exec_attempt = 0
            
            python_match = re.search(r"```python\s*(.*?)(?:```|$)", ai_content, re.S)
            
            df = _get_cached_df(request.backtest_id, record.symbol, record.start_date.strftime('%Y-%m-%d'), record.end_date.strftime('%Y-%m-%d'), record.timeframe)
            
            while python_match and exec_attempt <= MAX_EXEC_RETRIES:
                if df is None:
                    break
                    
                code = python_match.group(1)
                logger.info(f"[Historical Lab] Executing Python (attempt {exec_attempt + 1})...")
                execution_results = await run_python_code(code, symbol=record.symbol, inject_df=df.copy(), user_id=current_user["id"])

                if execution_results.get("success"):
                    logger.info(f"[Historical Lab] Code execution successful.")
                    break
                else:
                    error_msg = execution_results.get("error")
                    exec_attempt += 1
                    
                    if exec_attempt > MAX_EXEC_RETRIES:
                        logger.error(f"[Historical Lab] Code execution failed permanently.")
                        break
                        
                    logger.warning(f"[Historical Lab] Code attempt {exec_attempt} failed: {error_msg}. Retrying self-correction...")
                    
                    try:
                        # Provide specific guidance for common errors like IndexError
                        hint = ""
                        if "IndexError" in error_msg:
                            hint = " (HINT: You likely sliced the DataFrame too small before calculating an indicator like ATR, RSI, or SMA. Ensure the DataFrame has enough rows—at least 50 to 200—before passing it to 'ta' functions.)"
                        elif "NaN" in error_msg or "NoneType" in error_msg:
                            hint = " (HINT: Check for NaNs produced by indicators and use .dropna() or handle them before further calculations.)"
                        
                        correction_messages = messages + [
                            {"role": "assistant", "content": ai_content},
                            {"role": "user", "content": f"The Python code you provided failed with: {error_msg}{hint}. Please provide a FIXED version of the code block wrapped in ```python ... ```."}
                        ]
                        response = await client.chat.completions.create(
                            model=request.model,
                            messages=correction_messages,
                            temperature=0.1,
                            max_tokens=8192,
                            timeout=30
                        )
                        ai_content = response.choices[0].message.content or ""
                        full_raw_response = _capture_raw_response(response)
                        python_match = re.search(r"```python\s*(.*?)(?:```|$)", ai_content, re.S)
                    except Exception as ce:
                        logger.error(f"Self-correction failed: {ce}")
                        break

            # Build structured message
            ai_msg_data = {
                "role": "assistant", 
                "content": str(ai_content),
                "reasoning": reasoning_text,
                "raw_thinking": full_raw_response,
                "execution_output": execution_results.get("output") if execution_results else None,
                "execution_charts": execution_results.get("charts") if execution_results else None,
                "execution_tables": execution_results.get("tables") if execution_results else None,
            }
            
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
async def get_symbols(current_user: dict = Depends(get_current_user)):
    return {"symbols": AVAILABLE_SYMBOLS}

@router.get("/available-years/{symbol}")
async def get_years(symbol: str, current_user: dict = Depends(get_current_user)):
    years = get_available_years(symbol)
    return {"symbol": symbol, "years": years, "from": min(years) if years else None, "to": max(years) if years else None}
