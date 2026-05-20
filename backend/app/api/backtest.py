import os
import pandas as pd
import ta
import numpy as np
import json
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, update
from openai import AsyncOpenAI
from pathlib import Path

from ..core.config import settings
from ..core.security import get_current_user
from ..core.database import AsyncSessionLocal
from ..core.providers import PROVIDERS, get_api_key as _get_api_key, get_base_url
from ..models.ai_memory import UserPrompt, DefaultPromptStrategy
from ..models.historical_lab import HistoricalBacktest

router = APIRouter(prefix="/backtest", tags=["Backtest"])

PARQUET_DIR = Path(__file__).parent.parent.parent.parent / "data_archive" / "parquet_storage"

class BacktestRequest(BaseModel):
    prompt_id: str
    symbol: str
    timeframe: str = "1T"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    provider: Optional[str] = "nvidia"
    model: Optional[str] = "qwen/qwen3.5-122b-a10b"

class BacktestResponse(BaseModel):
    success: bool
    metrics: Optional[Dict[str, Any]] = None
    equity_curve: Optional[List[float]] = None
    error: Optional[str] = None
    generated_code: Optional[str] = None

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
        best = max(previous_results, key=lambda r: r.get("total_return", -999))
        worst = min(previous_results, key=lambda r: r.get("total_return", 999))
        improvement_context = f"""
PREVIOUS RESULTS for this strategy:
- Total runs: {len(previous_results)}
- Best result: {best.get('total_return', 'N/A')}% return, {best.get('win_rate', 'N/A')}% win rate, {best.get('max_drawdown', 'N/A')}% max drawdown
- Worst result: {worst.get('total_return', 'N/A')}% return, {worst.get('win_rate', 'N/A')}% win rate, {worst.get('max_drawdown', 'N/A')}% max drawdown

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

def run_vectorized_backtest(df, strategy_code):
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
        except: pass
        exec_globals = {"__builtins__": safe_builtins, "pd": pd, "np": np, "ta": ta, **_extra_libs}
        exec(strategy_code, exec_globals)
        calculate_signals = exec_globals.get('calculate_signals')
        
        if not calculate_signals:
            return {"error": "Function calculate_signals not found in generated code"}

        # 2. Get signals
        df = df.copy()
        df['signal'] = calculate_signals(df)
        
        # 3. Simple vectorized backtest
        # Calculate log returns
        df['returns'] = np.log(df['close'] / df['close'].shift(1))
        # Strategy returns (signal is for the NEXT candle, so shift it)
        df['strategy_returns'] = df['signal'].shift(1) * df['returns']
        
        # Cumulative returns
        df['cum_returns'] = df['strategy_returns'].cumsum().apply(np.exp)
        
        # Metrics
        total_return = (df['cum_returns'].iloc[-1] - 1) * 100
        win_rate = (df['strategy_returns'] > 0).sum() / (df['strategy_returns'] != 0).sum() * 100 if (df['strategy_returns'] != 0).sum() > 0 else 0
        max_drawdown = (df['cum_returns'] / df['cum_returns'].cummax() - 1).min() * 100
        
        # Equity curve for charting (sample to 100 points to keep it light)
        curve = df['cum_returns'].fillna(1.0).tolist()
        step = max(1, len(curve) // 100)
        sampled_curve = curve[::step]

        return {
            "metrics": {
                "total_return": round(total_return, 2),
                "win_rate": round(win_rate, 2),
                "max_drawdown": round(max_drawdown, 2),
                "trades": int((df['signal'] != 0).sum())
            },
            "equity_curve": sampled_curve
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
                prompt_file = str(Path(__file__).resolve().parent.parent.parent.parent / "backend" / "prompt_list.txt")
                with open(prompt_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines:
                        if line.startswith(f"{p_num}."):
                            prompt_text = line.split(".", 1)[1].strip()
                            break
            except: pass
            
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
        full_df = resampled

    # 4. Run Backtest with Auto-Retry / Self-Correction
    max_retries = 2
    last_error = None
    
    for attempt in range(max_retries):
        result = run_vectorized_backtest(full_df, strategy_code)
        
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
        except:
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
        generated_code=strategy_code
    )
