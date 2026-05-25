import os
import pandas as pd
import ta
import numpy as np
import json
import re
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, update
from openai import AsyncOpenAI
from pathlib import Path
import logging

from ..core.config import settings
from ..core.security import get_current_user
from ..core.database import AsyncSessionLocal
from ..core.providers import PROVIDERS, get_api_key as _get_api_key, get_base_url
from ..models.ai_memory import UserPrompt, DefaultPromptStrategy
from ..models.historical_lab import HistoricalBacktest

router = APIRouter(prefix="/backtest", tags=["Backtest"])

PARQUET_DIR = Path(__file__).parent.parent.parent.parent / "data_archive" / "parquet_storage"
PROMPT_FILE = str(Path(__file__).resolve().parent.parent.parent.parent / "backend" / "prompt_list.txt")

CONTRACT_MULTIPLIERS = {
    'XAUUSD': 100, 'XAGUSD': 5000, 'EURUSD': 100000, 'GBPUSD': 100000,
    'USDJPY': 100000, 'USDCAD': 100000, 'AUDUSD': 100000, 'NZDUSD': 100000,
    'GBPJPY': 100000, 'EURJPY': 100000, 'BTCUSD': 1, 'ETHUSD': 1,
    'US30': 10, 'SPX500': 50, 'NAS100': 20, 'DAX40': 25,
    'UK100': 10, 'JP225': 10,
}

class BacktestRequest(BaseModel):
    prompt_id: str
    symbol: str
    timeframe: str = "1T"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    provider: Optional[str] = "nvidia"
    model: Optional[str] = "qwen/qwen3.5-122b-a10b"
    lot_size: Optional[float] = 0.01

class BacktestResponse(BaseModel):
    success: bool
    metrics: Optional[Dict[str, Any]] = None
    equity_curve: Optional[List[float]] = None
    error: Optional[str] = None
    generated_code: Optional[str] = None
    trades: Optional[List[Dict[str, Any]]] = None

async def generate_strategy_code(prompt_text: str, provider: str = "nvidia", model: str = "qwen/qwen3.5-122b-a10b", error_msg: Optional[str] = None, previous_results: Optional[list] = None):
    api_key = _get_api_key(provider, settings)
    if not api_key:
        raise Exception(f"AI API Key for {provider} not configured")
    base_url = get_base_url(provider)

    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key
    )

    # Build context from previous runs
    improvement_context = ""
    if previous_results:
        def _get_metric(m: dict, *keys):
            for k in keys:
                v = m.get(k)
                if v is not None:
                    return v
            return None

        best = max(previous_results, key=lambda r: _get_metric(r, "total_return", "total_return_pct") or -999)
        worst = min(previous_results, key=lambda r: _get_metric(r, "total_return", "total_return_pct") or 999)

        def _fmt(m):
            return (
                f"{_get_metric(m, 'total_return', 'total_return_pct') or 'N/A'}% return, "
                f"{_get_metric(m, 'win_rate', 'win_rate_pct') or 'N/A'}% win rate, "
                f"{_get_metric(m, 'max_drawdown', 'max_drawdown_pct') or 'N/A'}% max drawdown"
            )
        improvement_context = f"""
PREVIOUS RESULTS for this strategy:
- Total runs: {len(previous_results)}
- Best result: {_fmt(best)}
- Worst result: {_fmt(worst)}

OBJECTIVE: Generate an IMPROVED version that outperforms the previous best result. Try different parameters, add filters, or combine indicators to increase return while reducing drawdown.
"""

    system_prompt = f"""You are a Quantitative Developer. Convert the following natural language trading strategy into a Python function.

RULES:
1. Use the variable 'df' which is a pandas DataFrame with columns: open, high, low, close, volume.
2. Use 'ta' library for technical indicators (e.g., ta.momentum.rsi, ta.trend.sma_indicator, ta.trend.ema_indicator).
3. The function must be named 'calculate_signals(df)'.
4. It must return a pandas Series named 'signal' where:
   - 1 = Buy Signal
   - -1 = Sell Signal
   - 0 = No Signal
5. Be precise with logic. If multiple conditions are mentioned, all must be met.
6. Output ONLY the code block, no explanations.

EXAMPLE:
```python
def calculate_signals(df):
    close = df['close']
    # RSI(14) < 30
    rsi = ta.momentum.rsi(close, window=14)
    # Price above 200 SMA
    sma200 = ta.trend.sma_indicator(close, window=200)
    
    signal = pd.Series(0, index=df.index)
    signal[(rsi < 30) & (df['close'] > sma200)] = 1
    signal[(rsi > 70)] = -1
    return signal
```
{improvement_context}"""
    
    user_content = f"Convert this strategy: {prompt_text}"
    if error_msg:
        user_content = f"Your previous code for this strategy: '{prompt_text}' failed with this error: {error_msg}. Please fix the code and return ONLY the corrected 'calculate_signals(df)' function."

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        temperature=0.1,
        timeout=60
    )

    code_content = response.choices[0].message.content or ""
    # Extract code block
    match = re.search(r"```python\s*(.*?)\s*```", code_content, re.S)
    if match:
        return match.group(1).strip()
    return code_content.strip()

def run_vectorized_backtest(df, strategy_code, lot_size=0.01, contract_multiplier=100):
    """Execute code and calculate PnL."""
    try:
        # 1. Execute strategy code to define function - RESTRICTED builtins for security
        import builtins as _real_builtins
        _SAFE_IMPORT_MODULES = {'pandas', 'numpy', 'ta', 'scipy', 'sklearn', 'math', 'json', 'random', 'itertools', 'collections', 'decimal', 'warnings'}
        def _safe_import(name, *args, **kwargs):
            base = name.split('.')[0]
            if base not in _SAFE_IMPORT_MODULES:
                raise ImportError(f"Module '{name}' is not allowed")
            return _real_builtins.__import__(name, *args, **kwargs)

        safe_builtins = {
            'abs': abs, 'all': all, 'any': any, 'bool': bool, 'True': True,
            'False': False, 'None': None, 'dict': dict, 'enumerate': enumerate,
            'float': float, 'int': int, 'isinstance': isinstance, 'len': len,
            'list': list, 'max': max, 'min': min, 'range': range,
            'round': round, 'sorted': sorted, 'str': str, 'sum': sum,
            'tuple': tuple, 'type': type, 'zip': zip,
            'Exception': Exception, 'ValueError': ValueError,
            'TypeError': TypeError, 'KeyError': KeyError,
            'IndexError': IndexError, 'ZeroDivisionError': ZeroDivisionError,
            '__import__': _safe_import,
        }
        _extra_libs = {}
        try:
            import scipy
            import sklearn
            _extra_libs["scipy"] = scipy
            _extra_libs["sklearn"] = sklearn
        except Exception:
            import traceback as _tb
            print(f"[backtest] Optional libs unavailable: {_tb.format_exc()}")
        exec_globals = {"__builtins__": safe_builtins, "pd": pd, "np": np, "ta": ta, **_extra_libs}
        exec(strategy_code, exec_globals)
        calculate_signals = exec_globals.get('calculate_signals')
        
        if not calculate_signals:
            return {"error": "Function calculate_signals not found in generated code"}

        import pandas as pd
        if not callable(calculate_signals):
            return {"error": f"calculate_signals is not callable (got {type(calculate_signals).__name__})"}

        # 2. Get signals
        try:
            signal = calculate_signals(df.copy())
        except Exception as sig_err:
            return {"error": f"calculate_signals() raised on execution:\n{traceback.format_exc()}"}

        if not isinstance(signal, pd.Series):
            return {"error": f"calculate_signals() must return a pandas Series, got {type(signal).__name__}"}

        df = df.copy()
        df['signal'] = signal

        # 3. Vectorized P&L
        df['returns'] = np.log(df['close'] / df['close'].shift(1))
        df['strategy_returns'] = df['signal'].shift(1) * df['returns']
        df['cum_returns'] = df['strategy_returns'].cumsum().apply(np.exp)

        # 4. Extract individual trades from signal transitions
        position = df['signal'].shift(1).fillna(0)
        pos_change = position.diff().fillna(0) != 0
        df['_pos_group'] = pos_change.cumsum()

        trades = []
        for group_id, group in df[position != 0].groupby('_pos_group'):
            first_signal = int(group['signal'].iloc[0])
            if first_signal not in (1, -1):
                continue  # skip signal=0 transitions
            direction = 'BUY' if first_signal == 1 else 'SELL'
            entry_idx = group.index[0]
            exit_idx = group.index[-1]

            entry_price = float(df.loc[entry_idx, 'open'])
            exit_price = float(df.loc[exit_idx, 'close'])
            entry_time = str(df.loc[entry_idx, 'datetime']) if 'datetime' in df.columns else ''
            exit_time = str(df.loc[exit_idx, 'datetime']) if 'datetime' in df.columns else ''

            if direction == 'BUY':
                pnl_points = exit_price - entry_price
            else:
                pnl_points = entry_price - exit_price

            pnl_pct = (pnl_points / entry_price) * 100 if entry_price else 0
            pnl_dollars = pnl_points * contract_multiplier * lot_size
            holding_period = len(group)

            trades.append({
                'entry_time': entry_time,
                'exit_time': exit_time,
                'direction': direction,
                'entry_price': round(entry_price, 5),
                'exit_price': round(exit_price, 5),
                'pnl_points': round(pnl_points, 2),
                'pnl_pct': round(pnl_pct, 2),
                'pnl_dollars': round(pnl_dollars, 2),
                'holding_period': holding_period,
            })

        # 5. Metrics
        total_return = (df['cum_returns'].iloc[-1] - 1) * 100
        winning_trades = sum(1 for t in trades if t['pnl_pct'] > 0)
        total_trades = len(trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        max_drawdown = (df['cum_returns'] / df['cum_returns'].cummax() - 1).min() * 100

        # Equity curve (sample to 100 points)
        curve = df['cum_returns'].fillna(1.0).tolist()
        step = max(1, len(curve) // 100)
        sampled_curve = curve[::step]

        return {
            "metrics": {
                "total_return": round(total_return, 2),
                "win_rate": round(win_rate, 2),
                "max_drawdown": round(max_drawdown, 2),
                "trades": total_trades,
            },
            "equity_curve": sampled_curve,
            "trades": trades,
        }
    except Exception as e:
        return {"error": str(e)}

@router.post("/run", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    
    # 1. Get Prompt Text and Strategy Code (Cache)
    strategy_code = None
    prompt_text = ""
    
    async with AsyncSessionLocal() as db:
        if request.prompt_id.startswith("custom_"):
            db_id = int(request.prompt_id.split("_")[1])
            result = await db.execute(select(UserPrompt).where(UserPrompt.id == db_id, UserPrompt.user_id == user_id))
            prompt_obj = result.scalar_one_or_none()
            if not prompt_obj:
                raise HTTPException(status_code=404, detail="Prompt not found")
            prompt_text = prompt_obj.content
            strategy_code = prompt_obj.strategy_code
        else:
            # Default prompts
            p_num = int(request.prompt_id)
            # Try to get prompt text from file
            try:
                with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines:
                        if line.startswith(f"{p_num}."):
                            prompt_text = line.split(".", 1)[1].strip()
                            break
            except Exception:
                pass
            
            # Check default strategy cache
            result = await db.execute(select(DefaultPromptStrategy).where(DefaultPromptStrategy.prompt_number == p_num))
            strategy_obj = result.scalar_one_or_none()
            if strategy_obj:
                strategy_code = strategy_obj.strategy_code

    # 2. Generate Code — query previous results for iterative improvement
    previous_results = []
    if prompt_text:
        async with AsyncSessionLocal() as db:
            prev_result = await db.execute(
                select(HistoricalBacktest).where(
                    HistoricalBacktest.prompt == prompt_text,
                    HistoricalBacktest.status == "completed",
                    HistoricalBacktest.metrics.isnot(None)
                ).order_by(HistoricalBacktest.created_at.desc()).limit(5)
            )
            prev_runs = prev_result.scalars().all()
            for run in prev_runs:
                if run.metrics:
                    previous_results.append(run.metrics)
    
    if not strategy_code:
        try:
            strategy_code = await generate_strategy_code(
                prompt_text, 
                provider=request.provider, 
                model=request.model,
                previous_results=previous_results if previous_results else None
            )
            # Save to cache
            async with AsyncSessionLocal() as db:
                if request.prompt_id.startswith("custom_"):
                    db_id = int(request.prompt_id.split("_")[1])
                    await db.execute(update(UserPrompt).where(UserPrompt.id == db_id).values(strategy_code=strategy_code))
                else:
                    new_cache = DefaultPromptStrategy(prompt_number=int(request.prompt_id), strategy_code=strategy_code)
                    db.add(new_cache)
                await db.commit()
        except Exception as e:
            return BacktestResponse(success=False, error=f"AI Generation failed: {str(e)}")

    # 3. Load Market Data
    start_dt = datetime.strptime(request.start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(request.end_date, "%Y-%m-%d")

    df_list = []
    for year in range(start_dt.year, end_dt.year + 1):
        file_path = PARQUET_DIR / f"{request.symbol}_{year}.parquet"
        if file_path.exists():
            df_list.append(pd.read_parquet(file_path))
    
    if not df_list:
        return BacktestResponse(success=False, error=f"No historical data found for {request.symbol} in range {request.start_date} to {request.end_date}")

    full_df = pd.concat(df_list).sort_values('timestamp')
    full_df['datetime'] = pd.to_datetime(full_df['timestamp'], unit='s')

    # Filter by date range
    full_df = full_df[(full_df['datetime'] >= start_dt) & (full_df['datetime'] <= end_dt.replace(hour=23, minute=59, second=59))]
    if full_df.empty:
        return BacktestResponse(success=False, error=f"No data for {request.symbol} between {request.start_date} and {request.end_date}")

    # Resample if needed (Parquet is M1)
    if request.timeframe != "1T":
        full_df.set_index('datetime', inplace=True)
        resampled = full_df.resample(request.timeframe).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        full_df = resampled.reset_index()  # keep datetime as a column

    # 4. Run Backtest with Auto-Retry / Self-Correction
    max_retries = 2
    last_error = None

    lot_size = request.lot_size or 0.01
    contract_multiplier = CONTRACT_MULTIPLIERS.get(request.symbol, 100)

    loop = asyncio.get_event_loop()
    for attempt in range(max_retries):
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, run_vectorized_backtest, full_df, strategy_code, lot_size, contract_multiplier),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            result = {"error": "Code execution timed out (30s limit). Simplify the strategy logic."}
        
        if "error" not in result:
            # Success! Break loop
            break
        
        last_error = result["error"]
        print(f"Backtest Attempt {attempt+1} failed: {last_error}. Retrying with correction...")
        
        # Call AI again with the error message
        try:
            strategy_code = await generate_strategy_code(
                prompt_text, 
                provider=request.provider,
                model=request.model,
                error_msg=last_error
            )
            # Update cache with fixed code
            async with AsyncSessionLocal() as db:
                if request.prompt_id.startswith("custom_"):
                    db_id = int(request.prompt_id.split("_")[1])
                    await db.execute(update(UserPrompt).where(UserPrompt.id == db_id).values(strategy_code=strategy_code))
                else:
                    await db.execute(update(DefaultPromptStrategy).where(DefaultPromptStrategy.prompt_number == int(request.prompt_id)).values(strategy_code=strategy_code))
                await db.commit()
        except Exception:
            logging.getLogger("backtest").error("AI retry generation failed", exc_info=True)
            # If AI generation fails during retry, stop
            break
    
    if "error" in result:
        return BacktestResponse(success=False, error=result["error"], generated_code=strategy_code)

    # 5. Save Backtest Record
    async with AsyncSessionLocal() as db:
        backtest_rec = HistoricalBacktest(
            user_id=user_id,
            symbol=request.symbol,
            start_date=start_dt,
            end_date=end_dt,
            timeframe=request.timeframe,
            mode="backtest",
            prompt=prompt_text,
            status="completed",
            metrics=result["metrics"],
            equity_curve=result["equity_curve"],
            generated_code=strategy_code
        )
        db.add(backtest_rec)
        await db.commit()

    return BacktestResponse(
        success=True,
        metrics=result["metrics"],
        equity_curve=result["equity_curve"],
        trades=result.get("trades"),
        generated_code=strategy_code
    )
