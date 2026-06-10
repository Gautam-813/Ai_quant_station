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
from ..models.ai_memory import AutopilotTrade, AutopilotSettings, UserPrompt, AutopilotLog
from ..models.strategy_score import StrategyScore

router = APIRouter(prefix="/autopilot", tags=["Autopilot"])


def _capture_raw_response(response) -> dict | None:
    try:
        return response.model_dump(mode='json')
    except Exception:
        try:
            return response.dict()
        except Exception:
            return None

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
    """Load prompts from file.

    Supports two formats:
      - Old: "1. Analyze XAUUSD..."
      - New: "PROMPT #1:\\nAnalyze XAUUSD price structure..."
    Returns list of "N. <full prompt text>" for backward compatibility.
    """
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []

    prompts = []
    current_num = None
    current_lines = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Check for new format: "PROMPT #N:"
        new_match = re.match(r"^PROMPT\s*#(\d+):?\s*$", line, re.I)
        if new_match:
            # Save previous prompt if any
            if current_num is not None and current_lines:
                text = " ".join(current_lines).strip()
                prompts.append(f"{current_num}. {text}")
            current_num = int(new_match.group(1))
            current_lines = []
            continue

        # Check for old format: "N. text"
        old_match = re.match(r"^(\d+)\.\s*(.*)", line)
        if old_match and current_num is None:
            # Save previous old-style prompt
            if current_num is not None and current_lines:
                text = " ".join(current_lines).strip()
                prompts.append(f"{current_num}. {text}")
            current_num = int(old_match.group(1))
            current_lines = [old_match.group(2)]
            continue

        # Accumulate content lines for the current prompt
        if current_num is not None:
            # Clean up extra whitespace
            cleaned = re.sub(r'\s+', ' ', line).strip()
            if cleaned:
                current_lines.append(cleaned)

    # Save the last prompt
    if current_num is not None and current_lines:
        text = " ".join(current_lines).strip()
        prompts.append(f"{current_num}. {text}")

    return prompts


def add_log(user_id: int, message: str, level: str = "INFO"):
    state = _get_state(user_id)
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    log_entry = {"timestamp": timestamp, "level": level, "message": message}
    state["logs"].append(log_entry)
    if len(state["logs"]) > 100:
        state["logs"] = state["logs"][-100:]
    # Persist to DB (fire-and-forget)
    cycle_number = state.get("stats", {}).get("total_runs")
    asyncio.create_task(_persist_log(user_id, level, message, cycle_number))


async def _persist_log(user_id: int, level: str, message: str, cycle_number: int | None = None):
    try:
        async with AsyncSessionLocal() as db:
            entry = AutopilotLog(
                user_id=user_id,
                level=level,
                message=message,
                cycle_number=cycle_number,
            )
            db.add(entry)
            await db.commit()
    except Exception:
        pass  # Log persistence should never crash the calling code


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

    # Safety limits — persist across server restarts by reading from DB
    today = datetime.now(timezone.utc).date()
    if state["stats"]["daily_reset_date"] != str(today):
        today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        today_end = today_start + timedelta(days=1)
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(
                    func.count(AutopilotTrade.id),
                    func.coalesce(func.sum(AutopilotTrade.profit), 0),
                ).where(
                    AutopilotTrade.user_id == user_id,
                    AutopilotTrade.executed_at >= today_start,
                    AutopilotTrade.executed_at < today_end,
                )
            )).one()
            state["stats"]["daily_trade_count"] = row[0]
            state["stats"]["daily_pnl"] = float(row[1])
        state["stats"]["daily_reset_date"] = str(today)

    if state["stats"]["daily_trade_count"] >= max_trades:
        add_log(user_id, f"Daily trade limit ({max_trades}) reached. Skipping.", "WARNING")
        state["stats"]["skipped_count"] += 1
        return

    # Score-weighted prompt selection (fallback to random if no scores)
    chosen = None
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(StrategyScore).where(
                    StrategyScore.symbol == symbol,
                    StrategyScore.total_trades >= 3,
                ).order_by(StrategyScore.win_rate.desc())
            )
            scores = result.scalars().all()

        if scores:
            weighted = []
            for p in prompt_pool:
                matching_scores = [
                    s for s in scores
                    if s.prompt_text == p["text"] and s.direction is None
                ]
                if matching_scores:
                    s = matching_scores[0]
                    weight = max(int(s.win_rate) - 30, 5) if s.total_trades >= 5 else 10
                else:
                    weight = 10
                weighted.extend([p] * weight)

            if weighted:
                chosen = random.choice(weighted)

    except Exception:
        pass

    if not chosen:
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
        if re.search(r'\b1[-\s]?(?:d|day|w|week)\b|daily|weekly|d1|w1|previous\s*day|yesterday', lower):
            return 3000
        if re.search(r'\b4[-\s]?(?:h|hour)\b|four[-\s]?hour|h4\b|4hrs?\b', lower):
            return 2000
        if re.search(r'\b1[-\s]?(?:h|hour)\b|one[-\s]?hour|hourly|h1\b|1hrs?\b', lower):
            return 1000
        return 500

    data_count = _detect_required_candles(prompt_text)
    market_data = await get_market_data(user_id, symbol, count=data_count, connector_url=connector_url)
    if not market_data or len(market_data) == 0:
        add_log(user_id, "No market data available", "ERROR")
        state["stats"]["error_count"] += 1
        return
    add_log(user_id, f"Loaded {len(market_data)} candles for {symbol} (requested {data_count})")

    # ── NEW: SANDBOX APPROACH ──────────────────────────────────────────
    # Instead of dumping raw candle text into the AI prompt, we:
    # 1. Ask AI to write analysis code (short prompt, ~150 tokens)
    # 2. Execute the code in sandbox with 1m OHLC data
    # 3. Parse TRADE_SETUP JSON or NO_SETUP from sandbox output
    # 4. Self-correct if code fails (up to 2 retries)

    error_feedback = state.get("last_error_feedback")
    error_section = ""
    if error_feedback:
        error_section = f"\nPREVIOUS TRADE ERROR FEEDBACK (learn from this):\n{error_feedback}\n- Adjust stop loss / take profit to be further from entry.\n- Do NOT repeat the same mistake.\n"

    code_prompt = f"""You are a quant trader. Write Python code to analyze 1-minute OHLC data.

The DataFrame `df` is already loaded with columns: open, high, low, close, volume, timestamp (Unix seconds).
Available (already importable): pandas (pd), numpy (np), ta, math, json, datetime.
Use pd.to_datetime() for datetime conversion.

Strategy to analyze:
{prompt_text}
{error_section}
INSTRUCTIONS:
1. Resample 1m data to appropriate timeframe (1H, 4H, or daily).
2. Compute indicators using `ta` library — exact values, no estimation.
3. If a high-confidence trade setup exists (confidence >= 60%), output JSON:
   ```json
   {{"action": "TRADE_SETUP", "symbol": "{symbol}", "direction": "BUY", "order_type": "market", "entry_price": 0.0, "stop_loss": 0.0, "take_profit": 0.0, "lot_size": {lot_size}, "reasoning": "Brief explanation", "confidence": 75}}
   ```
4. If NO setup, just print: NO_SETUP
5. Use print() for ALL output. Always consider risk-reward >= 1:2.
6. CRITICAL: Write TOP-LEVEL executable code. Do NOT wrap in functions/classes. If you use a function, call it at the end. The code runs immediately.

Respond ONLY with Python code inside ```python ... ``` block."""

    api_key = await resolve_api_key(provider, settings, user_id, AsyncSessionLocal)
    if not api_key:
        add_log(user_id, "No API key configured", "ERROR")
        state["stats"]["error_count"] += 1
        return

    if provider == "nvidia" and not api_key.startswith("nvapi-"):
        api_key = f"nvapi-{api_key}"

    # Step 1: AI generates analysis code
    generated_code = ""
    full_raw_response = None
    try:
        client = AsyncOpenAI(base_url=get_base_url(provider), api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": code_prompt}],
            temperature=0.2,
            max_tokens=2500,
            timeout=60
        )
        content = response.choices[0].message.content or ""
        full_raw_response = _capture_raw_response(response)
        match = re.search(r'```(?:python)?\n?(.*?)```', content, re.DOTALL)
        generated_code = match.group(1).strip() if match else content.strip()
        add_log(user_id, f"AI generated code ({len(generated_code)} chars)")
    except Exception as e:
        add_log(user_id, f"AI code generation failed: {str(e)}", "ERROR")
        state["stats"]["error_count"] += 1
        return

    # Step 2 & 3: Execute in sandbox with self-correction
    from ..api.execute import run_python_code

    setup = None
    ai_response = generated_code  # Store generated code as AI response for DB
    for attempt in range(3):
        try:
            sandbox_result = await run_python_code(
                code=generated_code,
                market_data=market_data,
                symbol=symbol,
                user_id=user_id,
            )
        except Exception as e:
            add_log(user_id, f"Sandbox execution error: {str(e)}", "ERROR")
            break

        if sandbox_result.get("success"):
            output = sandbox_result.get("output", "")

            # Try parse TRADE_SETUP from output (```json block or raw JSON)
            jm = re.search(r'```json\n?(.*?)```', output, re.DOTALL)
            if jm:
                try:
                    setup = json.loads(jm.group(1))
                    add_log(user_id, f"TRADE_SETUP found via sandbox (conf={setup.get('confidence')}%)")
                    break
                except json.JSONDecodeError:
                    pass

            if not setup:
                for line in output.strip().split("\n"):
                    line = line.strip()
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict) and obj.get("action") == "TRADE_SETUP":
                            setup = obj
                            break
                    except json.JSONDecodeError:
                        pass

            if setup:
                break

            if "NO_SETUP" in output:
                add_log(user_id, "Sandbox: NO_SETUP - No trade opportunity", "WARNING")
                state["stats"]["skipped_count"] += 1
                return

            # Unclear output — retry with feedback
            if attempt < 2:
                add_log(user_id, f"Sandbox output unclear, retrying...", "WARNING")
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "user", "content": code_prompt},
                            {"role": "assistant", "content": generated_code},
                            {"role": "user", "content": f"The code ran but didn't output a valid TRADE_SETUP or NO_SETUP. Fix it to output either format. Output was:\n{output[:300]}"}
                        ],
                        temperature=0.2,
                        max_tokens=2500,
                        timeout=60
                    )
                    content = response.choices[0].message.content or ""
                    match = re.search(r'```(?:python)?\n?(.*?)```', content, re.DOTALL)
                    generated_code = match.group(1).strip() if match else content.strip()
                    ai_response = generated_code
                except Exception as e:
                    add_log(user_id, f"AI correction failed: {str(e)}", "ERROR")
                    break
        else:
            # Sandbox error — self-correct
            if attempt < 2:
                error_msg = sandbox_result.get("error", "Unknown error")
                add_log(user_id, f"Code execution error, self-correcting...", "WARNING")
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "user", "content": code_prompt},
                            {"role": "assistant", "content": generated_code},
                            {"role": "user", "content": f"The code crashed. Fix the bug. Error:\n{error_msg[:500]}"}
                        ],
                        temperature=0.2,
                        max_tokens=2500,
                        timeout=60
                    )
                    content = response.choices[0].message.content or ""
                    match = re.search(r'```(?:python)?\n?(.*?)```', content, re.DOTALL)
                    generated_code = match.group(1).strip() if match else content.strip()
                    ai_response = generated_code
                except Exception as e:
                    add_log(user_id, f"AI correction failed: {str(e)}", "ERROR")
                    break
            else:
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
        state["last_error_feedback"] = None
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
                reasoning=reasoning, confidence=confidence, ai_response=ai_response, raw_thinking=full_raw_response, cycle_number=state["stats"]["total_runs"]
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

            # Dynamically determine the history window to check based on the oldest open trade
            try:
                oldest_trade = min(open_trades, key=lambda t: t.executed_at)
                executed_at = oldest_trade.executed_at
                if executed_at.tzinfo is None:
                    executed_at = executed_at.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                hours_diff = int((now_utc - executed_at).total_seconds() / 3600) + 12  # add 12h buffer
                sync_hours = max(hours_diff, 24)
            except Exception:
                sync_hours = 24

            try:
                history_data = await async_request("GET", f"{connector_url}/history", params={"hours": sync_hours})
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
                    exit_price = close_deal.get("price")
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
                    trade.exit_price = exit_price
                    trade.result = res_type
                    state["stats"]["daily_pnl"] = state["stats"].get("daily_pnl", 0) + profit
                    if closed_at_str:
                        trade.closed_at = datetime.strptime(closed_at_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                        if trade.executed_at:
                            if trade.executed_at.tzinfo is None:
                                trade.executed_at = trade.executed_at.replace(tzinfo=timezone.utc)
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
    exit_price: Optional[float] = None
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


class LogEntry(BaseModel):
    id: int
    timestamp: str
    level: str
    message: str
    cycle_number: Optional[int] = None


class LogsResponse(BaseModel):
    logs: List[LogEntry]
    total: int
    page: int
    per_page: int
    has_next: bool


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
            ).order_by(AutopilotTrade.executed_at.desc())
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


@router.get("/logs")
async def get_autopilot_logs(
    level: Optional[str] = None,
    cycle_number: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Get autopilot logs from DB with filters and pagination."""
    user_id = current_user["id"]
    per_page = min(per_page, 200)

    async with AsyncSessionLocal() as db:
        query = select(AutopilotLog).where(AutopilotLog.user_id == user_id)

        if level:
            query = query.where(AutopilotLog.level == level.upper())
        if cycle_number is not None:
            query = query.where(AutopilotLog.cycle_number == cycle_number)
        if from_date:
            try:
                fd = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                query = query.where(AutopilotLog.timestamp >= fd)
            except ValueError:
                pass
        if to_date:
            try:
                td = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
                query = query.where(AutopilotLog.timestamp < td)
            except ValueError:
                pass

        total_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_result.scalar() or 0

        query = query.order_by(AutopilotLog.timestamp.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await db.execute(query)
        rows = result.scalars().all()

        logs = [
            LogEntry(
                id=r.id,
                timestamp=r.timestamp.strftime("%Y-%m-%d %H:%M:%S") if r.timestamp else "",
                level=r.level,
                message=r.message,
                cycle_number=r.cycle_number,
            )
            for r in rows
        ]

    return LogsResponse(
        logs=logs,
        total=total,
        page=page,
        per_page=per_page,
        has_next=(page * per_page) < total,
    )


@router.get("/results", response_model=List[TradeResult])
async def get_trade_results(
    skip: int = 0,
    limit: int = 50,
    prompt_number: Optional[int] = None,
    prompt_text: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get trade results history."""
    limit = min(limit, 500)
    user_id = current_user["id"]

    async with AsyncSessionLocal() as db:
        query = (
            select(AutopilotTrade)
            .where(AutopilotTrade.user_id == user_id)
            .order_by(AutopilotTrade.executed_at.desc())
        )
        if prompt_number is not None:
            query = query.where(AutopilotTrade.prompt_number == prompt_number)
        if prompt_text is not None:
            query = query.where(AutopilotTrade.prompt_text == prompt_text)
        result = await db.execute(query.offset(skip).limit(limit))
        trades = result.scalars().all()

        return [
            TradeResult(
                id=t.id,
                prompt_number=t.prompt_number,
                prompt_text=t.prompt_text,
                symbol=t.symbol,
                direction=t.direction,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
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