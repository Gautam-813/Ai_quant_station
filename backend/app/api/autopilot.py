"""
Autopilot API - Automatic trading based on AI analysis
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import asyncio
import random
import os
import json
import re
from sqlalchemy import select, func
from openai import AsyncOpenAI
import httpx
import pandas as pd
import ta
import numpy as np

from ..core.config import settings
from ..core.security import get_current_user
from ..core.database import AsyncSessionLocal
from ..core.providers import PROVIDERS, get_api_key as _get_api_key, get_base_url, resolve_api_key
from ..core.utils import detect_trade_setup
from ..models.ai_memory import AutopilotTrade, AutopilotSettings, UserPrompt

router = APIRouter(prefix="/autopilot", tags=["Autopilot"])

_http_client: httpx.AsyncClient | None = None

def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client

async def shutdown_http_client():
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None

_user_states: Dict[int, dict] = {}
_user_locks: Dict[int, asyncio.Lock] = {}

def _get_state(user_id: int) -> dict:
    if user_id not in _user_states:
        _user_states[user_id] = {
            "enabled": False,
            "running": False,
            "logs": [],
            "task": None,
            "last_error_feedback": None,
            "stats": {
                "total_runs": 0,
                "trades_executed": 0,
                "skipped_count": 0,
                "error_count": 0,
                "last_run": None,
                "daily_trade_count": 0,
                "daily_pnl": 0.0,
                "daily_reset_date": None,
            }
        }
    return _user_states[user_id]

PROMPT_FILE = str(Path(__file__).resolve().parent.parent.parent.parent / "backend" / "prompt_list.txt")


def load_prompts():
    """Load prompts from file."""
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f.readlines() if line.strip() and "." in line]
    except Exception:
        return []


def add_log(user_id: int, message: str, level: str = "INFO"):
    state = _get_state(user_id)
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    log_entry = {"timestamp": timestamp, "level": level, "message": message}
    state["logs"].append(log_entry)
    if len(state["logs"]) > 100:
        state["logs"] = state["logs"][-100:]


async def async_request(method: str, url: str, **kwargs) -> dict:
    client = get_http_client()
    headers = kwargs.pop("headers", {})
    if settings.MT5_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.MT5_API_TOKEN}"
    kwargs["headers"] = headers
    response = await client.request(method, url, **kwargs)
    if not response.is_success:
        body = response.text[:500]
        raise Exception(f"HTTP {response.status_code}: {body}")
    return response.json()


async def initialize_mt5_connector(user_id: int, terminal_path: str = None, connector_url: str = None) -> bool:
    try:
        connector_url = (connector_url or settings.MT5_CONNECTOR_URL or "").strip() or None
        payload = {}
        if terminal_path:
            payload["terminal_path"] = terminal_path
        data = await async_request("POST", f"{connector_url}/initialize", json=payload)
        if data.get("success"):
            account = data.get("account", {})
            add_log(user_id, f"MT5 Connected: {account.get('server')} | Balance: ${account.get('balance', 0):.2f}", "SUCCESS")
            return True
        add_log(user_id, f"MT5 init failed", "ERROR")
    except Exception as e:
        add_log(user_id, f"MT5 connection error: {str(e)}", "ERROR")
    return False


async def get_market_data(user_id: int, symbol: str, timeframe: str = "1m", count: int = 500, connector_url: str = None):
    try:
        connector_url = (connector_url or settings.MT5_CONNECTOR_URL or "").strip() or None
        data = await async_request("GET", f"{connector_url}/data/latest/{symbol}", params={"timeframe": timeframe, "count": count})
        if data.get("success"):
            return data.get("data", [])
    except Exception as e:
        add_log(user_id, f"Failed to fetch market data: {str(e)}", "ERROR")
    return None


def _build_order_action(direction: str, order_type: str) -> str:
    """Build MT5 action string from direction and order type."""
    d = direction.upper()
    ot = (order_type or "market").lower()
    if ot == "market":
        return d  # "BUY" or "SELL"
    if ot == "limit":
        return f"{d}_LIMIT"  # "BUY_LIMIT" or "SELL_LIMIT"
    if ot == "stop":
        return f"{d}_STOP"  # "BUY_STOP" or "SELL_STOP"
    return d


async def execute_trade(user_id: int, symbol: str, direction: str, volume: float, entry_price: float = None,
                       sl: float = None, tp: float = None, comment: str = "[AUTOPILOT]", prompt_num: int = None,
                       connector_url: str = None, order_type: str = "market"):
    try:
        connector_url = (connector_url or settings.MT5_CONNECTOR_URL or "").strip() or None
        if prompt_num:
            if isinstance(prompt_num, int) and prompt_num < 0:
                trade_comment = f"[AUTOPILOT] Custom-{abs(prompt_num)}"
            else:
                trade_comment = f"[AUTOPILOT] P{prompt_num}"
        else:
            trade_comment = comment

        action = _build_order_action(direction, order_type)
        is_pending = order_type.lower() in ("limit", "stop")

        # Fetch symbol info for min stop distance + current price
        price = None
        min_dist = None
        digits = None
        try:
            sym_data = await async_request("GET", f"{connector_url}/symbol/{symbol}")
            price = sym_data.get("bid") or sym_data.get("ask")
            stops_level = sym_data.get("trade_stops_level") or sym_data.get("stops_level")
            point = sym_data.get("point")
            if stops_level is not None and point:
                min_dist = max(stops_level, 10) * point
            digits = sym_data.get("digits")
        except Exception as e:
            add_log(user_id, f"Could not fetch symbol info for {symbol}: {str(e)}", "ERROR")

        # Reference price for stop distance checks (current market for pending orders too)
        ref_price = price or entry_price

        # Apply minimum stop distance safeguard to SL
        if sl and sl > 0 and min_dist and ref_price and digits:
            sl = round(sl, digits)
            is_buy = direction.upper() == "BUY"
            if is_buy:
                if sl >= ref_price - min_dist:
                    adjusted = round(ref_price - min_dist, digits)
                    add_log(user_id, f"SL {sl} too close, adjusted to {adjusted}", "WARNING")
                    sl = adjusted
            else:
                if sl <= ref_price + min_dist:
                    adjusted = round(ref_price + min_dist, digits)
                    add_log(user_id, f"SL {sl} too close, adjusted to {adjusted}", "WARNING")
                    sl = adjusted

        # Minimum stop distance safeguard to TP
        if tp and tp > 0 and min_dist and ref_price and digits:
            tp = round(tp, digits)
            is_buy = direction.upper() == "BUY"
            if is_buy:
                if tp <= ref_price + min_dist:
                    adjusted = round(ref_price + min_dist, digits)
                    add_log(user_id, f"TP {tp} too close, adjusted to {adjusted}", "WARNING")
                    tp = adjusted
            else:
                if tp >= ref_price - min_dist:
                    adjusted = round(ref_price - min_dist, digits)
                    add_log(user_id, f"TP {tp} too close, adjusted to {adjusted}", "WARNING")
                    tp = adjusted

        payload = {"symbol": symbol, "action": action, "volume": volume, "comment": trade_comment}
        if is_pending:
            payload["price"] = entry_price
        if sl and sl > 0:
            payload["sl"] = sl
        if tp and tp > 0:
            payload["tp"] = tp

        data = await async_request("POST", f"{connector_url}/order", json=payload)
        if data.get("success"):
            return {"success": True, "ticket": data.get("ticket"), "price": data.get("price")}
        return {"success": False, "error": "Order failed"}
    except Exception as e:
        add_log(user_id, f"Trade execution failed: {str(e)}", "ERROR")
        return {"success": False, "error": str(e)}


async def check_open_positions(connector_url: str = None, user_id: int = 0):
    try:
        connector_url = (connector_url or settings.MT5_CONNECTOR_URL or "").strip() or None
        data = await async_request("GET", f"{connector_url}/positions")
        if data.get("success"):
            return data.get("positions", [])
    except Exception as e:
        import traceback as _tb
        add_log(user_id, f"check_open_positions error: {e}\n{_tb.format_exc()}", "ERROR")
    return []


async def run_autopilot_cycle(user_id: int):
    state = _get_state(user_id)
    default_prompts = load_prompts()
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AutopilotSettings).where(AutopilotSettings.user_id == user_id)
        )
        settings_obj = result.scalar_one_or_none()

        if not settings_obj:
            add_log(user_id, "Autopilot not configured", "ERROR")
            return

        result = await db.execute(
            select(UserPrompt).where(UserPrompt.user_id == user_id)
        )
        personal_prompts = result.scalars().all()

        symbol = settings_obj.symbol
        provider = settings_obj.provider
        model = settings_obj.model
        lot_size = settings_obj.default_lot
        terminal_path = settings_obj.mt5_terminal_path
        connector_url = settings_obj.mt5_connector_url
        mt5_connected = settings_obj.mt5_connected
        selected_ids = settings_obj.selected_prompts or []
        max_trades = settings_obj.max_trades_per_day
        max_loss = settings_obj.max_daily_loss
        cooldown = settings_obj.cooldown_minutes

    prompt_pool = []
    for line in default_prompts:
        try:
            p_num = int(line.split(".")[0].strip())
            if not selected_ids or p_num in selected_ids:
                prompt_pool.append({"id": p_num, "text": line.split(".", 1)[1].strip(), "is_custom": False})
        except Exception:
            continue

    for p in personal_prompts:
        custom_id = f"custom_{p.id}"
        if not selected_ids or custom_id in selected_ids:
            prompt_pool.append({"id": custom_id, "text": p.content, "is_custom": True})

    if not prompt_pool:
        add_log(user_id, "No prompts selected in settings", "ERROR")
        return

    if not mt5_connected:
        add_log(user_id, f"Initializing MT5 connection to {connector_url or 'default'}...")
        conn_ok = await initialize_mt5_connector(user_id, terminal_path, connector_url)
        if not conn_ok:
            hint = "Check connector URL." if connector_url else "Check terminal path."
            add_log(user_id, f"Failed to connect to MT5. {hint}", "ERROR")
            return
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AutopilotSettings).where(AutopilotSettings.user_id == user_id))
            s = result.scalar_one_or_none()
            if s:
                s.mt5_connected = True
                await db.commit()

    state["stats"]["total_runs"] += 1
    state["stats"]["last_run"] = datetime.now(timezone.utc).isoformat()
    add_log(user_id, f"=== Starting Cycle #{state['stats']['total_runs']} ===")

    # Safety limits
    today = datetime.now(timezone.utc).date()
    if state["stats"]["daily_reset_date"] != str(today):
        state["stats"]["daily_trade_count"] = 0
        state["stats"]["daily_pnl"] = 0.0
        state["stats"]["daily_reset_date"] = str(today)

    if state["stats"]["daily_trade_count"] >= max_trades:
        add_log(user_id, f"Daily trade limit ({max_trades}) reached. Skipping.", "WARNING")
        state["stats"]["skipped_count"] += 1
        return

    chosen = random.choice(prompt_pool)
    prompt_id_val = chosen["id"]
    prompt_text = chosen["text"]
    if chosen["is_custom"]:
        prompt_num = -int(prompt_id_val.split('_')[1])
        display_id = f"Custom-{prompt_id_val.split('_')[1]}"
    else:
        prompt_num = prompt_id_val
        display_id = f"#{prompt_num}"
    add_log(user_id, f"Using Strategy {display_id}: {prompt_text[:50]}...")

    # Detect required candle count based on prompt text
    def _detect_required_candles(text: str) -> int:
        lower = text.lower()
        if re.search(r'daily|weekly|d1|w1|previous\s*day|yesterday', lower):
            return 3000
        if re.search(r'4h\b|4[-\s]?hour|four\s*hour|h4\b|4hrs?\b', lower):
            return 2000
        if re.search(r'1h\b|1[-\s]?hour|one\s*hour|hourly|h1\b|1hrs?\b', lower):
            return 1000
        return 500

    data_count = _detect_required_candles(prompt_text)
    market_data = await get_market_data(user_id, symbol, count=data_count, connector_url=connector_url)
    if not market_data or len(market_data) == 0:
        add_log(user_id, "No market data available", "ERROR")
        state["stats"]["error_count"] += 1
        return
    add_log(user_id, f"Loaded {len(market_data)} candles for {symbol} (requested {data_count})")

    latest = market_data[-1]
    samples = []
    for c in market_data[-60:]:
        samples.append(f"O:{c.get('open', 0):.2f} H:{c.get('high', 0):.2f} L:{c.get('low', 0):.2f} C:{c.get('close', 0):.2f}")

    # Multi-TF: resample 1m data to higher timeframes for AI context
    multi_tf_section = ""
    try:
        df_1m = pd.DataFrame(market_data)
        df_1m['datetime'] = pd.to_datetime(df_1m['time'], unit='s') if 'time' in df_1m.columns else pd.to_datetime(df_1m['timestamp'], unit='s')
        df_1m = df_1m.set_index('datetime').sort_index()
        for c in ['open', 'high', 'low', 'close']:
            if c in df_1m.columns:
                df_1m[c] = pd.to_numeric(df_1m[c], errors='coerce')

        tf_lines = []
        for alias, suffix in [('1H', 'H1'), ('4H', 'H4'), ('1D', 'D1')]:
            df_tf = df_1m.resample(alias).agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
            }).dropna()
            if len(df_tf) < 5:
                continue
            tf_latest = df_tf.iloc[-1]
            close = df_tf['close'].astype(float)
            rsi = ta.momentum.rsi(close, window=14) if len(df_tf) >= 15 else pd.Series(50.0, index=df_tf.index)
            ema9 = ta.trend.ema_indicator(close, window=9) if len(df_tf) >= 10 else close
            ema50 = ta.trend.sma_indicator(close, window=50) if len(df_tf) >= 51 else close
            trend = "UP" if ema9.iloc[-1] > ema50.iloc[-1] else "DOWN" if ema9.iloc[-1] < ema50.iloc[-1] else "SIDEWAYS"
            tf_lines.append(
                f"{alias}: O={tf_latest['open']:.2f} H={tf_latest['high']:.2f} L={tf_latest['low']:.2f} C={tf_latest['close']:.2f} | "
                f"RSI(14)={rsi.iloc[-1]:.1f} EMA9={ema9.iloc[-1]:.2f} EMA50={ema50.iloc[-1]:.2f} Trend={trend}"
            )
        if tf_lines:
            multi_tf_section = "\nHIGHER TIMEFRAMES:\n" + "\n".join(tf_lines) + "\n"
            add_log(user_id, f"Multi-TF context built: {', '.join(l.split(':')[0] for l in tf_lines)}")

        # Previous day high/low from 1m data (group by calendar date)
        df_1m['date'] = df_1m.index.date
        dates = sorted(df_1m['date'].unique(), reverse=True)
        if len(dates) >= 2:
            prev_date = dates[1]
            today = dates[0]
            prev_mask = df_1m['date'] == prev_date
            prev_day = df_1m[prev_mask]
            today_data = df_1m[df_1m['date'] == today]
            prev_high = prev_day['high'].max()
            prev_low = prev_day['low'].min()
            prev_close = prev_day['close'].iloc[-1]
            today_open = today_data['open'].iloc[0]
            today_high = today_data['high'].max()
            today_low = today_data['low'].min()
            today_close_price = today_data['close'].iloc[-1]
            session_type = "BULLISH" if today_close_price > prev_close else "BEARISH" if today_close_price < prev_close else "RANGING"
            prev_line = (
                f"PREVIOUS DAY: Date={prev_date} High={prev_high:.2f} Low={prev_low:.2f} Close={prev_close:.2f} | "
                f"TODAY: Open={today_open:.2f} High={today_high:.2f} Low={today_low:.2f} | "
                f"Session={session_type}"
            )
            multi_tf_section += prev_line + "\n"
    except Exception as e:
        add_log(user_id, f"Multi-TF computation failed: {str(e)}", "WARNING")

    error_feedback = state.get("last_error_feedback")
    error_section = ""
    if error_feedback:
        error_section = f"""
PREVIOUS TRADE ERROR FEEDBACK (learn from this):
{error_feedback}
- Adjust your stop loss / take profit levels to be further from entry price.
- Ensure sufficient distance for broker minimum stop requirements.
- Do NOT repeat the same mistake.
"""

    system_prompt = f"""You are a Lead Quant in 2026. Analyze market data and find trade opportunities.

CURRENT MARKET DATA for {symbol}:
- Latest: O:{latest.get('open', 0):.2f} H:{latest.get('high', 0):.2f} L:{latest.get('low', 0):.2f} C:{latest.get('close', 0):.2f}

SAMPLES (Last 20 candles): {', '.join(samples)}
{multi_tf_section}{error_section}
ORDER TYPES:
- "market" — execute immediately at current price (for entry_price use null or current price)
- "limit" — pending order at a BETTER price (BUY_LIMIT below market, SELL_LIMIT above market). Set entry_price to desired level.
- "stop" — pending order at a WORSE/breakout price (BUY_STOP above market, SELL_STOP below market). Set entry_price to trigger level.

RULES:
1. Analyze the data and if a high-confidence trade setup exists (>=60% confidence), output a JSON block:

```json
{{"action": "TRADE_SETUP", "symbol": "{symbol}", "direction": "BUY", "order_type": "market", "entry_price": 2345.50, "stop_loss": 2338.00, "take_profit": 2360.00, "lot_size": {lot_size}, "risk_reward": 1.93, "reasoning": "Brief explanation", "confidence": 75}}
```

2. If NO clear setup, respond with "NO_SETUP" only
3. Choose the right order_type for market conditions (limit for pullbacks, stop for breakouts, market for strong momentum)
4. Always consider risk-reward ratio (1:2 or better)
5. Consider technical indicators (RSI, MACD, moving averages) if helpful
"""

    api_key = await resolve_api_key(provider, settings, user_id, AsyncSessionLocal)
    if not api_key:
        add_log(user_id, "No API key configured", "ERROR")
        state["stats"]["error_count"] += 1
        return

    if provider == "nvidia" and not api_key.startswith("nvapi-"):
        api_key = f"nvapi-{api_key}"

    try:
        client = AsyncOpenAI(base_url=get_base_url(provider), api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt_text}],
            temperature=0.2,
            timeout=60
        )
        ai_response = response.choices[0].message.content or ""
        add_log(user_id, f"AI Response (length: {len(ai_response)} chars)")
    except Exception as e:
        add_log(user_id, f"AI call failed: {str(e)}", "ERROR")
        state["stats"]["error_count"] += 1
        return

    max_retries = 2
    setup = None
    for attempt in range(max_retries):
        setup = detect_trade_setup(ai_response)
        if setup:
            break
        if "NO_SETUP" in ai_response:
            add_log(user_id, "AI Response: NO_SETUP - No trade opportunity found", "WARNING")
            state["stats"]["skipped_count"] += 1
            return
        add_log(user_id, f"Attempt {attempt+1}: No valid trade setup. Retrying...", "WARNING")
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_text},
                    {"role": "assistant", "content": ai_response},
                    {"role": "user", "content": "Your previous response was missing the TRADE_SETUP JSON block. Please provide your analysis again and include a valid JSON block in the exact format required."}
                ],
                temperature=0.2,
                timeout=60
            )
            ai_response = response.choices[0].message.content or ""
        except Exception as e:
            add_log(user_id, f"AI correction failed: {str(e)}", "ERROR")
            break

    if not setup:
        add_log(user_id, "Failed to get valid setup after retries", "ERROR")
        state["stats"]["skipped_count"] += 1
        return

    direction = setup.get("direction", "BUY").upper()
    order_type = setup.get("order_type", "market").lower()
    entry_price = setup.get("entry_price")
    sl = setup.get("stop_loss")
    tp = setup.get("take_profit")
    lot = setup.get("lot_size", lot_size)
    reasoning = setup.get("reasoning", "")
    confidence = setup.get("confidence", 70)

    add_log(user_id, f"TRADE SETUP - {direction} ({order_type}) | Entry: {entry_price} SL: {sl} TP: {tp} Lot: {lot} Confidence: {confidence}%")

    result = await execute_trade(user_id, symbol, direction, lot, entry_price, sl, tp, prompt_num=prompt_num, connector_url=connector_url, order_type=order_type)
    state["last_trade_time"] = datetime.now(timezone.utc)

    if result.get("success"):
        state["last_error_feedback"] = None  # Clear any previous error feedback
        ticket = result.get("ticket")
        exec_price = result.get("price")
        add_log(user_id, f"Trade executed - Ticket #{ticket} Price: {exec_price}", "SUCCESS")
        state["stats"]["trades_executed"] += 1
        state["stats"]["daily_trade_count"] += 1

        async with AsyncSessionLocal() as db:
            trade = AutopilotTrade(
                user_id=user_id, prompt_number=prompt_num, prompt_text=prompt_text,
                symbol=symbol, direction=direction, order_type=order_type, entry_price=entry_price,
                stop_loss=sl, take_profit=tp, lot_size=lot,
                mt5_ticket=ticket, execution_price=exec_price, execution_status="executed",
                reasoning=reasoning, confidence=confidence, ai_response=ai_response[:1000]
            )
            db.add(trade)
            await db.commit()
    else:
        error_msg = result.get('error', 'Unknown error')
        add_log(user_id, f"Trade failed: {error_msg}", "ERROR")
        state["last_error_feedback"] = (
            f"OrderType={order_type}, Direction={direction}, Entry={entry_price}, SL={sl}, TP={tp}, Lot={lot}. "
            f"Error: {error_msg}"
        )
        state["stats"]["error_count"] += 1


async def sync_trade_results(user_id: int, connector_url: str = None):
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AutopilotSettings).where(AutopilotSettings.user_id == user_id))
            settings_obj = result.scalar_one_or_none()
            if not settings_obj:
                return
            connector_url = (connector_url or settings_obj.mt5_connector_url or settings.MT5_CONNECTOR_URL or "").strip() or None

            result = await db.execute(
                select(AutopilotTrade).where(AutopilotTrade.user_id == user_id)
                .where(AutopilotTrade.execution_status == "executed").where(AutopilotTrade.result == None)
            )
            open_trades = result.scalars().all()
            if not open_trades:
                return

            try:
                history_data = await async_request("GET", f"{connector_url}/history", params={"hours": 24})
            except Exception as e:
                add_log(user_id, f"History fetch failed: {str(e)}", "ERROR")
                return

            if not history_data.get("success"):
                return
            deals = history_data.get("deals", [])
            if not deals:
                return

            updated_count = 0
            state = _get_state(user_id)
            for trade in open_trades:
                close_deal = None
                for deal in deals:
                    is_match = (deal.get("position_id") == trade.mt5_ticket or deal.get("ticket") == trade.mt5_ticket)
                    if is_match and deal.get("entry") == "CLOSE":
                        close_deal = deal
                        break
                if close_deal:
                    profit = close_deal.get("profit", 0)
                    closed_at_str = close_deal.get("time")
                    comment = close_deal.get("comment", "").lower()
                    res_type = "MANUAL_CLOSE"
                    if "sl" in comment:
                        res_type = "SL_HIT"
                    elif "tp" in comment:
                        res_type = "TP_HIT"
                    elif profit > 0:
                        res_type = "PROFIT"
                    else:
                        res_type = "LOSS"

                    trade.profit = profit
                    trade.result = res_type
                    state["stats"]["daily_pnl"] = state["stats"].get("daily_pnl", 0) + profit
                    if closed_at_str:
                        trade.closed_at = datetime.strptime(closed_at_str, '%Y-%m-%d %H:%M:%S')
                        if trade.executed_at:
                            diff = trade.closed_at - trade.executed_at
                            trade.duration_minutes = int(diff.total_seconds() / 60)
                    updated_count += 1
                    add_log(user_id, f"Trade #{trade.mt5_ticket} | Profit: ${profit:.2f} | {res_type}", "SUCCESS" if profit > 0 else "WARNING")

            if updated_count > 0:
                await db.commit()

    except Exception as e:
        add_log(user_id, f"Failed to sync trade results: {str(e)}", "ERROR")


async def autopilot_loop(user_id: int):
    state = _get_state(user_id)
    try:
        while state["enabled"]:
            if state["running"]:
                state["stats"]["daily_pnl"] = state["stats"].get("daily_pnl", 0)
                max_loss = None
                cooldown_mins = 0
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(AutopilotSettings).where(AutopilotSettings.user_id == user_id))
                    s = result.scalar_one_or_none()
                    if s:
                        max_loss = s.max_daily_loss
                        cooldown_mins = s.cooldown_minutes or 0

                # Cooldown check
                last_trade = state.get("last_trade_time")
                if cooldown_mins > 0 and last_trade:
                    elapsed_mins = (datetime.now(timezone.utc) - last_trade).total_seconds() / 60
                    if elapsed_mins < cooldown_mins:
                        add_log(user_id, f"Cooldown ({elapsed_mins:.0f}/{cooldown_mins} min). Skipping cycle.", "INFO")
                        state["stats"]["skipped_count"] += 1
                        async with AsyncSessionLocal() as db:
                            result = await db.execute(select(AutopilotSettings).where(AutopilotSettings.user_id == user_id))
                            s = result.scalar_one_or_none()
                            interval = s.interval_seconds if s else 300
                        if not state["enabled"]:
                            break
                        await asyncio.sleep(interval)
                        continue

                hit_loss_limit = False
                if max_loss is not None and state["stats"]["daily_pnl"] <= max_loss:
                    add_log(user_id, f"Daily loss limit (${max_loss}) reached. Stopping.", "WARNING")
                    state["running"] = False
                    hit_loss_limit = True
                await sync_trade_results(user_id)
                if not hit_loss_limit:
                    await run_autopilot_cycle(user_id)

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(AutopilotSettings).where(AutopilotSettings.user_id == user_id))
                s = result.scalar_one_or_none()
                interval = s.interval_seconds if s else 300
            # Only sleep if we're still enabled — skip sleep if stop was requested mid-cycle
            if not state["enabled"]:
                break
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        add_log(user_id, "Autopilot loop cancelled.", "INFO")


# Pydantic models
class AutopilotConfig(BaseModel):
    enabled: bool = False
    interval_seconds: int = 300
    default_lot: float = 0.10
    max_trades_per_day: int = 10
    cooldown_minutes: int = 5
    max_daily_loss: float = -50.0
    mt5_terminal_path: Optional[str] = None
    mt5_connector_url: Optional[str] = None
    symbol: str = "XAUUSD"
    provider: str = "nvidia"
    model: str = "qwen/qwen3.5-122b-a10b"
    selected_prompts: Optional[List] = None


class AutopilotStatus(BaseModel):
    enabled: bool
    running: bool
    settings: Optional[AutopilotConfig] = None
    stats: dict
    logs: List[dict]


class AutopilotStats(BaseModel):
    total_runs: int
    trades_executed: int
    skipped_count: int
    error_count: int
    last_run: Optional[str] = None


class UserPromptCreate(BaseModel):
    content: str


class UserPromptUpdate(BaseModel):
    content: str


class PromptResponse(BaseModel):
    id: str  # e.g., "1" or "custom_1"
    text: str
    is_custom: bool


class PromptStatus(BaseModel):
    default_prompts: List[PromptResponse]
    personal_prompts: List[PromptResponse]
    selected_ids: List


class TradeResult(BaseModel):
    id: int
    prompt_number: int
    prompt_text: str
    symbol: str
    direction: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    lot_size: float
    mt5_ticket: Optional[int]
    executed_at: str
    result: Optional[str]
    profit: Optional[float]
    closed_at: Optional[str]
    reasoning: Optional[str]
    confidence: Optional[float]


class PromptStatsItem(BaseModel):
    prompt_number: int
    prompt_text: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_profit: float
    avg_profit: float
    display_name: str = ""


# ── Internal helper: start autopilot without HTTP auth ────────────────────
async def _start_autopilot_internal(user_id: int) -> bool:
    """Start autopilot for a given user_id. Used for auto-restart on server boot."""
    state = _get_state(user_id)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AutopilotSettings).where(AutopilotSettings.user_id == user_id))
        settings_obj = result.scalar_one_or_none()
        if not settings_obj or not settings_obj.enabled:
            return False
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    async with _user_locks[user_id]:
        state["enabled"] = True
        state["running"] = True
        if state["task"] is None or state["task"].done():
            state["task"] = asyncio.create_task(autopilot_loop(user_id))
    add_log(user_id, "Autopilot auto-restarted after server boot")
    return True


# Endpoints
@router.post("/start")
async def start_autopilot(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    state = _get_state(user_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AutopilotSettings).where(AutopilotSettings.user_id == user_id))
        settings_obj = result.scalar_one_or_none()
        if not settings_obj:
            settings_obj = AutopilotSettings(user_id=user_id)
            db.add(settings_obj)
            await db.commit()
        if not settings_obj.enabled:
            settings_obj.enabled = True
            await db.commit()

    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()

    async with _user_locks[user_id]:
        state["enabled"] = True
        state["running"] = True
        if state["task"] is None or state["task"].done():
            state["task"] = asyncio.create_task(autopilot_loop(user_id))

    add_log(user_id, "Autopilot STARTED")
    return {"success": True, "message": "Autopilot started"}


@router.post("/stop")
async def stop_autopilot(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    state = _get_state(user_id)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AutopilotSettings).where(AutopilotSettings.user_id == user_id))
        s = result.scalar_one_or_none()
        if s:
            s.enabled = False
            await db.commit()
    state["enabled"] = False
    state["running"] = False
    # Cancel the background asyncio task so it cleanly exits the loop
    existing_task = state.get("task")
    if existing_task and not existing_task.done():
        existing_task.cancel()
        try:
            await existing_task
        except asyncio.CancelledError:
            pass
    state["task"] = None
    add_log(user_id, "Autopilot STOPPED")
    return {"success": True, "message": "Autopilot stopped"}


@router.get("/status", response_model=AutopilotStatus)
async def get_status(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    state = _get_state(user_id)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AutopilotSettings).where(AutopilotSettings.user_id == user_id))
        settings_obj = result.scalar_one_or_none()
        settings = None
        if settings_obj:
            settings = {
                "enabled": settings_obj.enabled, "interval_seconds": settings_obj.interval_seconds,
                "default_lot": settings_obj.default_lot, "max_trades_per_day": settings_obj.max_trades_per_day,
                "cooldown_minutes": settings_obj.cooldown_minutes, "max_daily_loss": settings_obj.max_daily_loss,
                "mt5_connector_url": settings_obj.mt5_connector_url,
                "symbol": settings_obj.symbol, "provider": settings_obj.provider, "model": settings_obj.model,
                "mt5_connected": settings_obj.mt5_connected,
                "selected_prompts": settings_obj.selected_prompts or []
            }
    return AutopilotStatus(enabled=state["enabled"], running=state["running"], settings=settings, stats=state["stats"], logs=state["logs"])


@router.post("/connect-mt5")
async def connect_mt5(
    terminal_path: Optional[str] = None,
    connector_url: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Connect to MT5 terminal."""
    user_id = current_user["id"]

    # Use URL from request param, or fall back to DB settings, or fall back to .env
    if not connector_url:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AutopilotSettings).where(AutopilotSettings.user_id == user_id)
            )
            settings_obj = result.scalar_one_or_none()
            if settings_obj:
                connector_url = (settings_obj.mt5_connector_url or "").strip() or None
                selected = settings_obj.selected_prompts or []
                if selected:
                    add_log(user_id, f"Active prompts: {len(selected)} selected ({', '.join(str(s) for s in selected)})")

    add_log(user_id, f"Connecting to MT5 at {connector_url or 'default'}...")

    success = await initialize_mt5_connector(user_id, terminal_path, connector_url)

    if success:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AutopilotSettings).where(AutopilotSettings.user_id == user_id)
            )
            settings_obj = result.scalar_one_or_none()

            if not settings_obj:
                settings_obj = AutopilotSettings(user_id=user_id)
                db.add(settings_obj)

            if terminal_path:
                settings_obj.mt5_terminal_path = terminal_path
            if connector_url:
                settings_obj.mt5_connector_url = connector_url
            settings_obj.mt5_connected = True
            await db.commit()

        return {"success": True, "message": "Connected to MT5 successfully"}
    else:
        return {"success": False, "message": "Failed to connect to MT5"}


@router.post("/settings")
async def save_settings(
    config: AutopilotConfig,
    current_user: dict = Depends(get_current_user)
):
    """Save autopilot settings."""
    user_id = current_user["id"]

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AutopilotSettings).where(AutopilotSettings.user_id == user_id)
        )
        settings_obj = result.scalar_one_or_none()

        if not settings_obj:
            settings_obj = AutopilotSettings(user_id=user_id)
            db.add(settings_obj)

        url_changed = config.mt5_connector_url is not None and config.mt5_connector_url != settings_obj.mt5_connector_url
        settings_obj.interval_seconds = config.interval_seconds
        settings_obj.default_lot = config.default_lot
        settings_obj.max_trades_per_day = config.max_trades_per_day
        settings_obj.cooldown_minutes = config.cooldown_minutes
        settings_obj.max_daily_loss = config.max_daily_loss
        settings_obj.mt5_terminal_path = config.mt5_terminal_path
        settings_obj.mt5_connector_url = config.mt5_connector_url
        settings_obj.symbol = config.symbol
        settings_obj.provider = config.provider
        settings_obj.model = config.model
        settings_obj.selected_prompts = config.selected_prompts
        if url_changed:
            settings_obj.mt5_connected = False
            add_log(user_id, "Connector URL changed — MT5 connection reset. Please reconnect.", "WARNING")

        await db.commit()

    state = _get_state(user_id)
    state["settings"] = config.model_dump()
    return {"success": True}


@router.get("/prompts", response_model=PromptStatus)
async def get_prompts(current_user: dict = Depends(get_current_user)):
    """Get all available prompts and current selection."""
    user_id = current_user["id"]
    
    # 1. Load defaults
    defaults_raw = load_prompts()
    defaults = []
    for line in defaults_raw:
        try:
            parts = line.split(".", 1)
            defaults.append(PromptResponse(
                id=parts[0].strip(),
                text=parts[1].strip(),
                is_custom=False
            ))
        except Exception:
            continue
            
    # 2. Load personal from DB
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserPrompt).where(UserPrompt.user_id == user_id)
        )
        personal_objs = result.scalars().all()
        personal = [PromptResponse(
            id=f"custom_{p.id}",
            text=p.content,
            is_custom=True
        ) for p in personal_objs]
        
        # 3. Get selected IDs
        result = await db.execute(
            select(AutopilotSettings.selected_prompts).where(AutopilotSettings.user_id == user_id)
        )
        selected_ids = result.scalar() or []
        
    return PromptStatus(
        default_prompts=defaults,
        personal_prompts=personal,
        selected_ids=selected_ids
    )


@router.post("/prompts")
async def create_prompt(data: UserPromptCreate, current_user: dict = Depends(get_current_user)):
    """Create a personal prompt."""
    user_id = current_user["id"]
    async with AsyncSessionLocal() as db:
        new_p = UserPrompt(user_id=user_id, content=data.content)
        db.add(new_p)
        await db.commit()
        await db.refresh(new_p)
        return {"success": True, "id": f"custom_{new_p.id}"}


@router.put("/prompts/{prompt_id}")
async def update_prompt(prompt_id: str, data: UserPromptUpdate, current_user: dict = Depends(get_current_user)):
    """Update a personal prompt."""
    user_id = current_user["id"]
    if not prompt_id.startswith("custom_"):
        raise HTTPException(status_code=400, detail="Cannot edit default prompts")
        
    db_id = int(prompt_id.split("_")[1])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserPrompt).where(UserPrompt.id == db_id, UserPrompt.user_id == user_id)
        )
        prompt = result.scalar_one_or_none()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
            
        prompt.content = data.content
        await db.commit()
        return {"success": True}


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(prompt_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a personal prompt."""
    user_id = current_user["id"]
    if not prompt_id.startswith("custom_"):
        raise HTTPException(status_code=400, detail="Cannot delete default prompts")
        
    db_id = int(prompt_id.split("_")[1])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserPrompt).where(UserPrompt.id == db_id, UserPrompt.user_id == user_id)
        )
        prompt = result.scalar_one_or_none()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
            
        await db.delete(prompt)
        
        # Also remove from selected_prompts if present
        result = await db.execute(
            select(AutopilotSettings).where(AutopilotSettings.user_id == user_id)
        )
        settings_obj = result.scalar_one_or_none()
        if settings_obj and settings_obj.selected_prompts:
            if prompt_id in settings_obj.selected_prompts:
                new_selected = [s for s in settings_obj.selected_prompts if s != prompt_id]
                settings_obj.selected_prompts = new_selected
                
        await db.commit()
        return {"success": True}


@router.get("/prompt-stats", response_model=List[PromptStatsItem])
async def get_prompt_stats(current_user: dict = Depends(get_current_user)):
    """Get win-rate statistics per prompt."""
    user_id = current_user["id"]

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AutopilotTrade).where(
                AutopilotTrade.user_id == user_id,
                AutopilotTrade.profit.isnot(None)
            )
        )
        trades = result.scalars().all()

    groups: dict[int, dict] = {}
    for t in trades:
        pn = t.prompt_number
        if pn not in groups:
            groups[pn] = {"prompt_number": pn, "prompt_text": t.prompt_text, "total_trades": 0, "wins": 0, "total_profit": 0.0}
        groups[pn]["total_trades"] += 1
        groups[pn]["total_profit"] += t.profit or 0
        if (t.profit or 0) > 0:
            groups[pn]["wins"] += 1

    stats = []
    for g in groups.values():
        g["losses"] = g["total_trades"] - g["wins"]
        g["win_rate"] = round(g["wins"] / g["total_trades"] * 100, 1) if g["total_trades"] > 0 else 0.0
        g["avg_profit"] = round(g["total_profit"] / g["total_trades"], 2) if g["total_trades"] > 0 else 0.0
        g["total_profit"] = round(g["total_profit"], 2)
        pn = g["prompt_number"]
        g["display_name"] = f"Custom-{abs(pn)}" if pn < 0 else f"#{pn}"
        stats.append(PromptStatsItem(**g))

    stats.sort(key=lambda x: x.total_profit, reverse=True)
    return stats


@router.get("/results", response_model=List[TradeResult])
async def get_trade_results(
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """Get trade results history."""
    limit = min(limit, 500)
    user_id = current_user["id"]

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AutopilotTrade)
            .where(AutopilotTrade.user_id == user_id)
            .order_by(AutopilotTrade.executed_at.desc())
            .offset(skip)
            .limit(limit)
        )
        trades = result.scalars().all()

        return [
            TradeResult(
                id=t.id,
                prompt_number=t.prompt_number,
                prompt_text=t.prompt_text,
                symbol=t.symbol,
                direction=t.direction,
                entry_price=t.entry_price,
                stop_loss=t.stop_loss,
                take_profit=t.take_profit,
                lot_size=t.lot_size,
                mt5_ticket=t.mt5_ticket,
                executed_at=t.executed_at.isoformat() if t.executed_at else "",
                result=t.result,
                profit=t.profit,
                closed_at=t.closed_at.isoformat() if t.closed_at else None,
                reasoning=t.reasoning,
                confidence=t.confidence
            )
            for t in trades
        ]


@router.get("/results/export")
async def export_trades_csv(current_user: dict = Depends(get_current_user)):
    """Export trade history as CSV."""
    import io, csv
    user_id = current_user["id"]

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AutopilotTrade)
            .where(AutopilotTrade.user_id == user_id)
            .order_by(AutopilotTrade.executed_at.desc())
        )
        trades = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Prompt #", "Prompt Text", "Symbol", "Direction", "Entry Price",
                      "Stop Loss", "Take Profit", "Lot Size", "Ticket", "Executed At",
                      "Result", "Profit", "Closed At", "Duration (min)", "Reasoning", "Confidence"])
    for t in trades:
        writer.writerow([
            t.id, t.prompt_number, t.prompt_text, t.symbol, t.direction,
            t.entry_price or "", t.stop_loss or "", t.take_profit or "",
            t.lot_size, t.mt5_ticket or "",
            t.executed_at.isoformat() if t.executed_at else "",
            t.result or "", t.profit or "",
            t.closed_at.isoformat() if t.closed_at else "",
            t.duration_minutes or "", t.reasoning or "", t.confidence or ""
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=autopilot_trades.csv"}
    )