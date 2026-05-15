import os
import pandas as pd
import pandas_ta as ta
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
from ..models.ai_memory import UserPrompt, DefaultPromptStrategy
from ..models.historical_lab import HistoricalBacktest

router = APIRouter(prefix="/backtest", tags=["Backtest"])

PARQUET_DIR = Path(r"D:\date-wise\06-04-2026(live current autopilot)\impulse_analyst_v2\data_archive\parquet_storage")

class BacktestRequest(BaseModel):
    prompt_id: str  # e.g., "1" or "custom_1"
    symbol: str
    timeframe: str = "1T"
    start_year: int = 2024
    end_year: int = 2024

class BacktestResponse(BaseModel):
    success: bool
    metrics: Optional[Dict[str, Any]] = None
    equity_curve: Optional[List[float]] = None
    error: Optional[str] = None
    generated_code: Optional[str] = None

def _get_api_key(provider: str = "nvidia") -> str:
    key_map = {
        "nvidia": "NVIDIA_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPEN_ROUTER_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    env_key = key_map.get(provider)
    if env_key:
        val = getattr(settings, env_key, "")
        if provider == "nvidia" and val and not val.startswith("nvapi-"):
            return f"nvapi-{val}"
        return val
    return ""

async def generate_strategy_code(prompt_text: str):
    """Call AI to convert prompt to rule-based Python code."""
    api_key = _get_api_key("nvidia")
    if not api_key:
        raise Exception("NVIDIA_API_KEY not configured")

    client = AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

    system_prompt = """You are a Quantitative Developer. Convert the following natural language trading strategy into a Python function.

RULES:
1. Use the variable 'df' which is a pandas DataFrame with columns: open, high, low, close, volume.
2. Use 'pandas_ta' (imported as 'ta') for technical indicators.
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
    # RSI(14) < 30
    rsi = df.ta.rsi(length=14)
    # Price above 200 SMA
    sma200 = df.ta.sma(length=200)
    
    signal = pd.Series(0, index=df.index)
    signal[(rsi < 30) & (df['close'] > sma200)] = 1
    signal[(rsi > 70)] = -1
    return signal
```
"""

    response = await client.chat.completions.create(
        model="qwen/qwen3.5-122b-a10b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Convert this strategy: {prompt_text}"}
        ],
        temperature=0.1
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
        # 1. Execute strategy code to define function
        exec_globals = {"pd": pd, "np": np, "ta": ta}
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
                prompt_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompt_list.txt")
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

    # 2. Generate Code if not cached
    if not strategy_code:
        try:
            strategy_code = await generate_strategy_code(prompt_text)
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
    df_list = []
    for year in range(request.start_year, request.end_year + 1):
        file_path = PARQUET_DIR / f"{request.symbol}_{year}.parquet"
        if file_path.exists():
            df_list.append(pd.read_parquet(file_path))
    
    if not df_list:
        return BacktestResponse(success=False, error=f"No historical data found for {request.symbol} in range {request.start_year}-{request.end_year}")

    full_df = pd.concat(df_list).sort_values('timestamp')
    # Resample if needed (Parquet is M1)
    if request.timeframe != "1T":
        # e.g. "15T", "1H"
        full_df['datetime'] = pd.to_datetime(full_df['timestamp'], unit='s')
        full_df.set_index('datetime', inplace=True)
        resampled = full_df.resample(request.timeframe).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        full_df = resampled

    # 4. Run Backtest
    result = run_vectorized_backtest(full_df, strategy_code)
    
    if "error" in result:
        return BacktestResponse(success=False, error=result["error"], generated_code=strategy_code)

    # 5. Save Backtest Record
    async with AsyncSessionLocal() as db:
        backtest_rec = HistoricalBacktest(
            user_id=user_id,
            symbol=request.symbol,
            start_date=datetime(request.start_year, 1, 1),
            end_date=datetime(request.end_year, 12, 31),
            timeframe=request.timeframe,
            mode="backtest",
            prompt=prompt_text,
            status="completed",
            metrics=result["metrics"],
            equity_curve=result["equity_curve"]
        )
        db.add(backtest_rec)
        await db.commit()

    return BacktestResponse(
        success=True,
        metrics=result["metrics"],
        equity_curve=result["equity_curve"],
        generated_code=strategy_code
    )
