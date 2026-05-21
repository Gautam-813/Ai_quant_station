from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
import json
import re
import asyncio
import logging
import traceback
from datetime import datetime, timezone
from time import time
import httpx
from openai import AsyncOpenAI
from openai import RateLimitError, APIError, Timeout
from .execute import run_python_code


from ..core.config import settings
from ..core.security import get_current_user
from ..core.database import AsyncSessionLocal
from ..models.market_data import MarketData
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy import select, func
from ..models.schemas import (
    ChatRequest,
    ChatResponse,
    AIProvider,
    AIProvidersResponse,
    MemoryResponse,
    MemoryInsight,
    MemoryStats,
    FeedbackRequest,
)
from ..models.ai_memory import (
    ChatMemory,
    UserPreferences,
    UserFeedback,
    GlobalInsights,
    ModelUsage,
)
from ..core.providers import PROVIDERS, get_api_key as _get_api_key, get_base_url

router = APIRouter(prefix="/ai", tags=["AI"])

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2
REQUEST_TIMEOUT = 30


async def _cache_market_data_internal(symbol: str, timeframe: str, data: List[dict], source: str):
    """Internal helper to cache market data in ai.py."""
    try:
        async with AsyncSessionLocal() as db:
            records = []
            for d in data:
                dt_time = d.get("time")
                if isinstance(dt_time, str):
                    try:
                        dt_time = datetime.strptime(dt_time, '%Y-%m-%d %H:%M:%S')
                    except:
                        dt_time = datetime.fromisoformat(dt_time.replace('Z', '+00:00'))
                elif isinstance(dt_time, (int, float)):
                    # Handle Unix timestamp
                    dt_time = datetime.fromtimestamp(dt_time)
                
                records.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "time": dt_time,
                    "open": d.get("open") or d.get("Open"),
                    "high": d.get("high") or d.get("High"),
                    "low": d.get("low") or d.get("Low"),
                    "close": d.get("close") or d.get("Close"),
                    "tick_volume": d.get("tick_volume") or d.get("Volume"),
                    "source": source
                })

            if not records:
                return

            stmt = sqlite_insert(MarketData).values(records)
            stmt = stmt.on_conflict_do_nothing()
            await db.execute(stmt)
            await db.commit()
    except Exception as e:
                logger.warning(f"AI Cache Error: {e}")


_model_cache = {"data": {}, "timestamp": 0}
MODEL_CACHE_TTL = 300  # 5 minutes


async def _fetch_live_models(provider_id: str, config: dict, api_key: str) -> Optional[List[str]]:
    """Fetch available models from provider API. Returns None on failure."""
    if not api_key:
        return None
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        if provider_id == "nvidia" and not api_key.startswith("nvapi-"):
            headers["Authorization"] = f"Bearer nvapi-{api_key}"

        base = config["base_url"].rstrip("/")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base}/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = [
                    item["id"] for item in data.get("data", []) if item.get("id")
                ]
                if models:
                    return sorted(models)
    except Exception as e:
        logger.warning(f"Could not fetch live models for {provider_id}: {e}")
    return None


@router.get("/providers", response_model=AIProvidersResponse)
async def get_providers(current_user: dict = Depends(get_current_user)):
    """Get available AI providers with live model lists."""
    now = time()
    if now - _model_cache["timestamp"] < MODEL_CACHE_TTL and _model_cache["data"]:
        return AIProvidersResponse(providers=_model_cache["data"])

    providers_list = []
    for key, value in PROVIDERS.items():
        api_key = _get_api_key(key, settings)
        live_models = await _fetch_live_models(key, value, api_key)
        providers_list.append(
            AIProvider(
                id=key,
                name=value["name"],
                base_url=value["base_url"],
                models=live_models if live_models else value["models"],
            )
        )

    _model_cache["data"] = providers_list
    _model_cache["timestamp"] = now
    return AIProvidersResponse(providers=providers_list)


@router.post("/test")
async def test_connection(
    provider: str, model: str, current_user: dict = Depends(get_current_user)
):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider")
    api_key = _get_api_key(provider, settings)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"No API key configured for {provider}")
    try:
        client = AsyncOpenAI(base_url=get_base_url(provider), api_key=api_key)
        await client.models.list()
        return {"success": True, "message": "Connection successful"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")


@router.post("/chat", response_model=ChatResponse)
async def chat(chat_req: ChatRequest, current_user: dict = Depends(get_current_user)):
    if chat_req.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider")
    api_key = _get_api_key(chat_req.provider, settings)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"No API key for {chat_req.provider}")
    provider_config = PROVIDERS[chat_req.provider]

    try:
        logger.info(f"[AI] Received - symbol: {chat_req.symbol}, candle_data: {len(chat_req.candle_data) if chat_req.candle_data else 0}")
        
        # Fetch market data if requested
        market_context = ""
        candle_data_for_ai = []  # Store for prompt
        # Use candle data if provided directly, or if load_market_data is set with symbol
        if chat_req.candle_data or (chat_req.load_market_data and chat_req.symbol):
            # Limit incoming candle data to prevent OOM
            if chat_req.candle_data and len(chat_req.candle_data) > 5000:
                chat_req.candle_data = chat_req.candle_data[-5000:]
            period = chat_req.data_period or "1mo"
            
            # USE INCOMING CANDLE DATA FROM FRONTEND (Priority)
            mt5_success = False
            candle_data_for_ai = chat_req.candle_data or []
            
            if candle_data_for_ai:
                print(f"[AI] Building market context with {len(candle_data_for_ai)} candles")
                # Use the candle data directly from frontend
                latest = candle_data_for_ai[-1]
                samples = []
                for c in candle_data_for_ai[-10:]:
                    samples.append(f"O:{c['open']:.2f} H:{c['high']:.2f} L:{c['low']:.2f} C:{c['close']:.2f}")
                
                market_context = f"""
Current market data for {chat_req.symbol or 'Unknown'} (Source: MT5):
- Latest: Open={latest['open']:.2f} High={latest['high']:.2f} Low={latest['low']:.2f} Close={latest['close']:.2f}
- Latest Time: {latest['time']}

SAMPLES (Last 10 candles): {', '.join(samples)}
"""
                mt5_success = True
                logger.info(f"[AI] Market context built - using {len(candle_data_for_ai)} candles")

            # FALLBACK TO YAHOO if no candle data and yahoo requested
            elif not mt5_success and chat_req.load_market_data == "yahoo":
                import yfinance as yf
                try:
                    ticker = yf.Ticker(chat_req.symbol)
                    hist = ticker.history(period=period)
                    if not hist.empty:
                        latest = hist.iloc[-1]
                        hist_tail = hist.tail(10)
                        market_context = f"""
Current market data for {chat_req.symbol} (Source: Yahoo Finance):
- Latest: Open={latest["Open"]:.2}, High={latest["High"]:.2}, Low={latest["Low"]:.2}, Close={latest["Close"]:.2}
- Volume: {latest["Volume"]}

Last 10 candles:
{hist_tail.to_string()}
"""
                        # Cache Yahoo data too
                        yahoo_records = []
                        for idx, row in hist.iterrows():
                            yahoo_records.append({
                                "time": idx.strftime('%Y-%m-%d %H:%M:%S'),
                                "open": float(row['Open']),
                                "high": float(row['High']),
                                "low": float(row['Low']),
                                "close": float(row['Close']),
                                "tick_volume": int(row['Volume'])
                            })
                        await _cache_market_data_internal(chat_req.symbol, "1d", yahoo_records, "yahoo")
                except Exception as e:
                    market_context = f"\n[Note: Could not fetch data for {chat_req.symbol}: {str(e)}]\n"

        # Fetch user memory (previous conversations about same symbol)
        user_memory_context = ""
        global_memory_context = ""

        async with AsyncSessionLocal() as db:
            try:
                # User's previous conversations about this symbol
                if chat_req.symbol:
                    result = await db.execute(
                        select(ChatMemory)
                        .where(
                            ChatMemory.user_id == current_user["id"],
                            ChatMemory.symbol == chat_req.symbol,
                        )
                        .order_by(ChatMemory.created_at.desc())
                        .limit(10)
                    )
                    prev_chats = result.scalars().all()

                    if prev_chats:
                        recent_context = []
                        for chat in reversed(prev_chats[:5]):  # Last 5 messages
                            role_label = "User" if chat.role == "user" else "AI"
                            content_preview = (
                                chat.content[:100] + "..."
                                if len(chat.content) > 100
                                else chat.content
                            )
                            recent_context.append(f"{role_label}: {content_preview}")

                        if recent_context:
                            user_memory_context = (
                                f"\n[Your recent chats about {chat_req.symbol}:\n"
                                + "\n".join(recent_context)
                                + "\n]"
                            )

                # Global memory (anonymized aggregated insights)
                global_result = await db.execute(
                    select(ChatMemory)
                    .where(
                        ChatMemory.symbol == chat_req.symbol,
                        ChatMemory.detected_setup.isnot(None),
                    )
                    .order_by(ChatMemory.created_at.desc())
                    .limit(20)
                )
                global_chats = global_result.scalars().all()

                if global_chats:
                    setups = []
                    for chat in global_chats:
                        if chat.detected_setup:
                            setups.append(
                                chat.detected_setup.get("direction", "UNKNOWN")
                            )

                    if setups:
                        buy_count = setups.count("BUY")
                        sell_count = setups.count("SELL")
                        global_memory_context = f"\n[Community insights for {chat_req.symbol}: {buy_count} BUY signals, {sell_count} SELL signals suggested recently]"
            except Exception as e:
                logger.warning(f"Memory fetch error: {e}")

        # Build messages with current conversation + memory context
        messages = []

        # Build professional system prompt (matching Streamlit)
        system_parts = [
            "You are a Lead Quant in 2026 with expertise in forex, crypto, and indices trading.",
            "",
            "RULES (STRICT):",
            "1. Analyze only based on the provided market data. Never use local system time.",
            "2. If you identify a trade opportunity, provide analysis + JSON block in this exact format:",
            "",
            "```json",
            '{"action": "TRADE_SETUP", "symbol": "XAUUSD", "direction": "BUY", "order_type": "market", "entry_price": 2345.50, "stop_loss": 2338.00, "take_profit": 2360.00, "lot_size": 0.10, "risk_reward": 1.93, "reasoning": "Brief explanation"}',
            "```",
            "",
            "IMPORTANT: JSON must be valid - every key-value pair must have a comma after it except the last one.",
            "",
            "3. For position management (analyzing open positions), use:",
            "```json",
            '{"action": "MODIFY_SLTP", "ticket": 123456, "new_sl": 2345.50, "new_tp": 2370.00, "reasoning": "Trail SL to lock profit"}',
            "```",
            "Available actions: CLOSE_POSITION, MODIFY_SL, MODIFY_TP, MODIFY_SLTP, ADD_TO_POSITION",
            "",
            "4. Always consider risk-reward ratios (1:2 or better preferred)",
            "5. Never guarantee profits - always mention risk",
            "6. If unsure, say so rather than guessing.",
            "7. Provide clear, actionable analysis with specific entry, SL, and TP levels.",
            "",
            "8. For technical indicator calculations (ATR, SMA, EMA, RSI, etc.):",
            "   - You have a global variable 'df' available which contains the COMPLETE historical dataset (1000+ candles).",
            "   - NEVER calculate indicators manually. Always write a Python code block (```python) to perform calculations.",
            "   - Use 'df' directly in your code. It is already loaded and ready.",
            "   - Output your results using print() or show_chart() functions.",
            "",
            "9. For visualizing numeric series or analysis results, use:",
            "```json",
            '{"action": "SHOW_CHART", "title": "RSI (14)", "data": [45.2, 48.5, 52.1, 50.4, 49.8], "color": "#22c55e"}',
            "```",
            "OR use show_chart(data, title) within your Python code block.",
            "",
            "10. For displaying tables, use show_table(df, title) within your Python code block.",
        ]

        # Add market data if available (like Streamlit - include full data samples)
        if market_context:
            system_parts.append(f"\nCurrent market data:\n{market_context}")
        
        # Add raw candle data if available (Streamlit style)
        if candle_data_for_ai:
            latest_time = candle_data_for_ai[-1].get('time', 'N/A')
            total_candles = len(candle_data_for_ai)
            samples = []
            for c in candle_data_for_ai[-5:]:  # Last 5 for quick text reference
                samples.append(f"O:{c.get('open')} H:{c.get('high')} L:{c.get('low')} C:{c.get('close')}")
            system_parts.append(f"\nLATEST_CANDLE_TIME: {latest_time}")
            system_parts.append(f"TOTAL_CANDLES_IN_DF: {total_candles}")
            system_parts.append(f"LATEST_SAMPLES: {', '.join(samples)}")
            system_parts.append("\nNote: The 'df' variable in the Python environment contains ALL these candles. Use it for your calculations.")

        # Add current session context (recent conversation from database)
        if user_memory_context:
            system_parts.append(f"\n{user_memory_context}")

        # Add global insights (community data)
        if global_memory_context:
            system_parts.append(f"\n{global_memory_context}")

        system_prompt = "\n".join(system_parts)
        messages.append({"role": "system", "content": system_prompt})

        # Add the current conversation from frontend
        # This is the MAIN conversation - previous messages in this chat
        for m in chat_req.messages:
            messages.append({"role": m.role, "content": m.content})

        logger.info(f"[AI Chat] === Starting AI Request ===")
        logger.info(f"[AI Chat] Provider: {chat_req.provider}")
        logger.info(f"[AI Chat] Model: {chat_req.model}")
        logger.info(f"[AI Chat] Base URL: {provider_config['base_url']}")
        logger.info(f"[AI Chat] API Key configured: {bool(api_key)}")
        
        client = AsyncOpenAI(base_url=provider_config["base_url"], api_key=api_key)
        logger.info(f"[AI Chat] OpenAI client created successfully")

        # Professional retry logic with detailed logging
        assistant_message = None
        last_error = "Unknown error - check server logs"
        
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"[AI Chat] Attempt {attempt + 1}/{MAX_RETRIES} - Making API call...")
                
                response = await client.chat.completions.create(
                    model=chat_req.model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=8192,
                    timeout=REQUEST_TIMEOUT
                )
                
                # Handle both content and reasoning_content (Qwen model uses reasoning_content)
                msg = response.choices[0].message
                assistant_message = msg.content or msg.reasoning_content or ""
                logger.info(f"[AI Chat] SUCCESS - Response length: {len(assistant_message)} chars")
                break
                
            except RateLimitError as e:
                last_error = f"Rate limit exceeded: {str(e)}"
                logger.warning(f"[AI Chat] Rate limit error: {str(e)}")
                
            except APIError as e:
                last_error = f"API error: {str(e)}"
                logger.warning(f"[AI Chat] API error: {str(e)}")
                
            except Exception as e:
                last_error = f"Error: {type(e).__name__}: {str(e)}"
                logger.error(f"[AI Chat] Exception: {type(e).__name__}: {str(e)}")
                logger.error(f"[AI Chat] Traceback: {traceback.format_exc()}")
            
            # If not last attempt, wait before retry
            if attempt < MAX_RETRIES - 1:
                logger.info(f"[AI Chat] Waiting {RETRY_DELAY}s before retry...")
                await asyncio.sleep(RETRY_DELAY)
        
        if assistant_message is None:
            logger.error(f"[AI Chat] All {MAX_RETRIES} attempts failed. Last error: {last_error}")
            raise HTTPException(
                status_code=503,
                detail=f"AI service unavailable after {MAX_RETRIES} attempts. Last error: {last_error}"
            )

        # Parse for trade setup or action
        detected_setup = _detect_trade_setup(assistant_message)
        detected_action = _detect_trade_action(assistant_message)
        
        # AUTOMATIC CODE EXECUTION with Self-Correction
        execution_output = None
        exec_data_preview = None
        exec_charts = None
        exec_tables = None
        
        # Initial code detection - use a robust regex that handles missing closing backticks
        python_match = re.search(r"```python\s*(.*?)(?:```|$)", assistant_message, re.S)
        if python_match:
            code = python_match.group(1)
            logger.info(f"[AI Chat] Detected Python code block - executing...")
            
            exec_res = await run_python_code(code, candle_data_for_ai, chat_req.symbol)
            
            # Self-Correction Loop
            if not exec_res.get("success"):
                error_msg = exec_res.get("error")
                logger.warning(f"[AI Chat] Code execution failed: {error_msg}. Attempting self-correction...")
                
                try:
                    # Ask the AI to fix its own code
                    correction_messages = messages + [
                        {"role": "assistant", "content": assistant_message},
                        {"role": "user", "content": f"The Python code you provided failed with this error: {error_msg}. Please provide a FIXED version of the code block."}
                    ]
                    
                    response = await client.chat.completions.create(
                        model=chat_req.model,
                        messages=correction_messages,
                        temperature=0.1,
                        max_tokens=8192
                    )
                    
                    assistant_message = response.choices[0].message.content or ""
                    # Try executing the NEW code - use the same robust regex
                    new_match = re.search(r"```python\s*(.*?)(?:```|$)", assistant_message, re.S)
                    if new_match:
                        code = new_match.group(1)
                        exec_res = await run_python_code(code, candle_data_for_ai, chat_req.symbol)
                except Exception as e:
                    logger.error(f"[AI Chat] Self-correction failed: {str(e)}")

            # Handle final result (success or failure)
            if exec_res.get("success"):
                execution_output = exec_res.get("output")
                exec_data_preview = exec_res.get("data_preview")
                exec_charts = exec_res.get("charts")
                exec_tables = exec_res.get("tables")
                logger.info(f"[AI Chat] Code executed (final attempt).")
            else:
                execution_output = f"Error executing code: {exec_res.get('error')}"
                logger.error(f"[AI Chat] Code execution failed permanently.")

        # Combine data previews
        final_data_preview = exec_data_preview or _detect_data_preview(assistant_message)


        # Save to database for memory
        saved_chat_memory_id = None
        async with AsyncSessionLocal() as db:
            try:
                user_msg = ChatMemory(
                    user_id=current_user["id"], symbol=chat_req.symbol,
                    role="user", content=chat_req.messages[-1].content if chat_req.messages else "",
                )
                db.add(user_msg)
                await db.commit()
                await db.refresh(user_msg)

                assistant_msg = ChatMemory(
                    user_id=current_user["id"], symbol=chat_req.symbol,
                    role="assistant", content=assistant_message,
                    detected_setup=detected_setup, detected_action=detected_action,
                )
                db.add(assistant_msg)
                await db.commit()
                await db.refresh(assistant_msg)
                saved_chat_memory_id = assistant_msg.id

                if chat_req.symbol and detected_setup:
                    result = await db.execute(select(GlobalInsights).where(GlobalInsights.symbol == chat_req.symbol))
                    insight = result.scalar_one_or_none()
                    if insight:
                        insight.total_analyzed += 1
                        if detected_setup.get("direction") == "BUY": insight.buy_signals += 1
                        else: insight.sell_signals += 1
                        insight.last_updated = datetime.now(timezone.utc)
                    else:
                        insight = GlobalInsights(symbol=chat_req.symbol, total_analyzed=1,
                            buy_signals=1 if detected_setup.get("direction") == "BUY" else 0,
                            sell_signals=1 if detected_setup.get("direction") == "SELL" else 0)
                        db.add(insight)
                    await db.commit()

                usage_result = await db.execute(select(ModelUsage).where(
                    ModelUsage.provider == chat_req.provider, ModelUsage.model == chat_req.model,
                    ModelUsage.user_id == current_user["id"]))
                usage = usage_result.scalar_one_or_none()
                if usage:
                    usage.total_requests += 1
                    usage.last_used = datetime.now(timezone.utc)
                else:
                    usage = ModelUsage(provider=chat_req.provider, model=chat_req.model,
                        user_id=current_user["id"], total_requests=1)
                    db.add(usage)
                await db.commit()
            except Exception as e:
                logger.warning(f"Failed to save chat memory: {e}")

        return ChatResponse(
            message=assistant_message,
            detected_setup=detected_setup,
            detected_action=detected_action,
            data_preview=final_data_preview,
            detected_chart=_detect_chart(assistant_message),
            execution_output=execution_output,
            execution_charts=exec_charts,
            execution_tables=exec_tables,
            chat_memory_id=saved_chat_memory_id
        )




    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"[AI Chat] Unhandled error: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"AI service error: {str(e)}"
        )


def _detect_trade_setup(text: str) -> Optional[dict]:
    """Detect TRADE_SETUP JSON from AI response."""
    json_pattern = r"```json\s*(.*?)\s*```"
    blocks = re.findall(json_pattern, text, re.S | re.I)

    for block in blocks:
        try:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                return data
        except json.JSONDecodeError:
            pass

    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
            return data
    except:
        pass

    return None


def _detect_trade_action(text: str) -> Optional[dict]:
    """Detect TRADE_ACTION JSON from AI response."""
    json_pattern = r"```json\s*(.*?)\s*```"
    blocks = re.findall(json_pattern, text, re.S | re.I)

    for block in blocks:
        try:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("action") in (
                "CLOSE_POSITION",
                "MODIFY_SL",
                "MODIFY_TP",
                "MODIFY_SLTP",
                "ADD_TO_POSITION",
            ):
                return data
        except json.JSONDecodeError:
            pass

    return None


def _detect_data_preview(text: str) -> Optional[str]:
    """Detect data preview (DataFrame tail) in AI response."""
    if "DataFrame shape:" in text and "Last" in text and "rows:" in text:
        # Extract from "DataFrame shape:" to the end of the table
        match = re.search(r"(DataFrame shape:.*?\n.*?(?:\n\s*\d+.*)+)", text, re.S)
        if match:
            return match.group(1).strip()
    
    # Also look for any table-like structure if it's explicitly marked
    if "DATA_PREVIEW:" in text:
        parts = text.split("DATA_PREVIEW:")
        if len(parts) > 1:
            return parts[1].strip().split("\n\n")[0]
            
    return None


def _detect_chart(text: str) -> Optional[dict]:
    """Detect SHOW_CHART JSON from AI response."""
    json_pattern = r"```json\s*(.*?)\s*```"
    blocks = re.findall(json_pattern, text, re.S | re.I)

    for block in blocks:
        try:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("action") == "SHOW_CHART":
                return data
        except json.JSONDecodeError:
            pass

    return None




# Memory endpoints
@router.get("/memory", response_model=MemoryResponse)
async def get_memory(skip: int = 0, limit: int = 20, current_user: dict = Depends(get_current_user)):
    """Get memory/insights."""
    limit = min(limit, 100)
    async with AsyncSessionLocal() as db:
        try:
            # Get recent conversations
            result = await db.execute(
                select(ChatMemory)
                .where(ChatMemory.user_id == current_user["id"])
                .order_by(ChatMemory.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            conversations = result.scalars().all()

            conv_list = []
            for c in conversations:
                conv_list.append(
                    {
                        "id": c.id,
                        "symbol": c.symbol,
                        "role": c.role,
                        "content": c.content[:200] + "..."
                        if len(c.content) > 200
                        else c.content,
                        "detected_setup": c.detected_setup,
                        "created_at": c.created_at.isoformat()
                        if c.created_at
                        else None,
                    }
                )

            # Get stats
            total_result = await db.execute(
                select(func.count(ChatMemory.id)).where(
                    ChatMemory.user_id == current_user["id"]
                )
            )
            total_conversations = total_result.scalar() or 0

            # Get preferences
            pref_result = await db.execute(
                select(UserPreferences).where(
                    UserPreferences.user_id == current_user["id"]
                )
            )
            pref = pref_result.scalar_one_or_none()

            prefs_dict = {}
            if pref:
                prefs_dict = {
                    "favorite_symbols": json.loads(pref.favorite_symbols)
                    if pref.favorite_symbols
                    else [],
                    "default_provider": pref.default_provider,
                    "default_model": pref.default_model,
                    "default_data_source": pref.default_data_source,
                    "default_period": pref.default_period,
                }

            return MemoryResponse(
                conversations=conv_list,
                insights=[],
                preferences=prefs_dict,
                stats=MemoryStats(
                    total_conversations=total_conversations,
                    total_trades_suggested=0,
                    successful_trades=0,
                    failed_trades=0,
                    win_rate=0.0,
                ),
            )
        except Exception as e:
            logger.warning(f"Memory error: {e}")
        return MemoryResponse(
            conversations=[],
            insights=[],
            preferences={},
            stats=MemoryStats(
                total_conversations=0,
                total_trades_suggested=0,
                successful_trades=0,
                failed_trades=0,
                win_rate=0.0,
            ),
        )


@router.post("/feedback")
async def save_feedback(
    feedback: FeedbackRequest, current_user: dict = Depends(get_current_user)
):
    """Save user feedback."""
    async with AsyncSessionLocal() as db:
        try:
            fb = UserFeedback(
                user_id=current_user["id"],
                is_helpful=feedback.rating >= 3,
                notes=feedback.feedback_text,
            )
            db.add(fb)
            await db.commit()
            return {"success": True, "message": "Feedback saved"}
        except Exception as e:
            return {"success": False, "message": str(e)}
