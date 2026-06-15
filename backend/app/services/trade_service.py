import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select

from ..core.database import AsyncSessionLocal
from ..models.ai_memory import TradeRecord, PositionAudit
from ..models.schemas import OrderRequest, CloseRequest, ModifyRequest

logger = logging.getLogger(__name__)


def _get_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        return None


def _get_safe_attr(attr, fallback):
    mt5 = _get_mt5()
    return getattr(mt5, attr) if hasattr(mt5, attr) else fallback


ORDER_FILLING_FOK = _get_safe_attr('ORDER_FILLING_FOK', 1)
ORDER_FILLING_IOC = _get_safe_attr('ORDER_FILLING_IOC', 2)
ORDER_FILLING_RETURN = _get_safe_attr('ORDER_FILLING_RETURN', 3)
TRADE_ACTION_DEAL = _get_safe_attr('TRADE_ACTION_DEAL', 1)
TRADE_ACTION_PENDING = _get_safe_attr('TRADE_ACTION_PENDING', 5)
TRADE_ACTION_SLTP = _get_safe_attr('TRADE_ACTION_SLTP', 6)
ORDER_TYPE_BUY = _get_safe_attr('ORDER_TYPE_BUY', 0)
ORDER_TYPE_SELL = _get_safe_attr('ORDER_TYPE_SELL', 1)

ACTION_MAP = {
    "BUY": ORDER_TYPE_BUY,
    "SELL": ORDER_TYPE_SELL,
    "BUY_LIMIT": _get_safe_attr('ORDER_TYPE_BUY_LIMIT', 2),
    "SELL_LIMIT": _get_safe_attr('ORDER_TYPE_SELL_LIMIT', 3),
    "BUY_STOP": _get_safe_attr('ORDER_TYPE_BUY_STOP', 4),
    "SELL_STOP": _get_safe_attr('ORDER_TYPE_SELL_STOP', 5),
}

PENDING_ACTIONS = frozenset({"BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP"})


class TradeError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def init_mt5() -> None:
    mt5 = _get_mt5()
    if mt5 is None:
        raise TradeError("MT5 not installed on this server", 500)
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, mt5.initialize)
    if not ok:
        error = mt5.last_error() if hasattr(mt5, 'last_error') else "Unknown"
        raise TradeError(f"MT5 initialization failed: {error}", 500)


async def _select_symbol(symbol: str):
    mt5 = _get_mt5()
    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, mt5.symbol_select, symbol, True):
        raise TradeError(f"Symbol {symbol} not found", 404)

    symbol_info = await loop.run_in_executor(None, mt5.symbol_info, symbol)
    tick = await loop.run_in_executor(None, mt5.symbol_info_tick, symbol)

    if symbol_info is None or tick is None:
        raise TradeError(f"Broker data unavailable for {symbol}", 400)

    return symbol_info, tick


async def place_order(order: OrderRequest, user_id: Optional[int]) -> dict:
    await init_mt5()
    mt5 = _get_mt5()
    loop = asyncio.get_running_loop()

    symbol_info, tick = await _select_symbol(order.symbol)

    if order.volume < symbol_info.volume_min:
        raise TradeError(f"Volume {order.volume} below minimum {symbol_info.volume_min}")

    volume = round(order.volume / symbol_info.volume_step) * symbol_info.volume_step
    volume = round(volume, 2)
    point = symbol_info.point
    digits = symbol_info.digits

    if order.action not in ACTION_MAP:
        raise TradeError(f"Invalid action: {order.action}")

    order_type = ACTION_MAP[order.action]
    is_pending = order.action in PENDING_ACTIONS

    if is_pending and order.price is None:
        raise TradeError("Price required for pending orders")

    if is_pending:
        price = order.price
    elif order.action == "BUY":
        price = tick.ask
    else:
        price = tick.bid

    if price is None:
        raise TradeError("Cannot get current price", 500)

    price = round(price, digits)

    min_dist = max(symbol_info.trade_stops_level, 10) * point

    sl = None
    if order.sl is not None:
        sl = round(order.sl, digits)
        if "BUY" in order.action:
            if sl >= price - min_dist:
                sl = round(price - min_dist, digits)
        else:
            if sl <= price + min_dist:
                sl = round(price + min_dist, digits)

    tp = None
    if order.tp is not None:
        tp = round(order.tp, digits)
        if "BUY" in order.action:
            if tp <= price + min_dist:
                tp = round(price + min_dist, digits)
        else:
            if tp >= price - min_dist:
                tp = round(price - min_dist, digits)

    request = {
        "action": TRADE_ACTION_DEAL if not is_pending else TRADE_ACTION_PENDING,
        "symbol": order.symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": 20,
        "magic": order.magic,
        "comment": order.comment,
        "type_time": mt5.ORDER_TIME_GTC if hasattr(mt5, 'ORDER_TIME_GTC') else 0,
        "type_filling": ORDER_FILLING_IOC,
    }

    if sl is not None:
        request["sl"] = sl
    if tp is not None:
        request["tp"] = tp

    if not is_pending:
        filling_mode = symbol_info.filling_mode
        if filling_mode & 1:
            request["type_filling"] = ORDER_FILLING_FOK
        elif filling_mode & 2:
            request["type_filling"] = ORDER_FILLING_IOC
        else:
            request["type_filling"] = ORDER_FILLING_RETURN

    result = await loop.run_in_executor(None, mt5.order_send, request)

    if result is None or result.retcode != getattr(mt5, 'TRADE_RETCODE_DONE', 10009):
        detail = result.comment if result else "Unknown error"
        raise TradeError(f"Order failed: {detail}")

    try:
        async with AsyncSessionLocal() as db:
            trade_rec = TradeRecord(
                user_id=user_id or 0,
                symbol=order.symbol,
                direction="BUY" if "BUY" in order.action else "SELL",
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                volume=volume,
                order_type="market" if not is_pending else "pending",
                status="open",
                mt5_ticket=result.order,
                executed_at=datetime.now(timezone.utc),
                comment=order.comment,
                ai_message=str(order.chat_memory_id) if order.chat_memory_id else None,
            )
            db.add(trade_rec)
            await db.commit()
    except Exception:
        logger.warning(f"Failed to save trade record for ticket {result.order}:\n{traceback.format_exc()}")

    return {
        "success": True,
        "ticket": result.order,
        "symbol": order.symbol,
        "action": order.action,
        "volume": volume,
        "price": price,
        "sl": sl,
        "tp": tp,
        "comment": result.comment,
    }


async def close_position(ticket: int, close_volume: Optional[float], user_id: Optional[int]) -> dict:
    await init_mt5()
    mt5 = _get_mt5()
    loop = asyncio.get_running_loop()

    positions = await loop.run_in_executor(None, lambda: mt5.positions_get(ticket=ticket))
    if positions is None or len(positions) == 0:
        raise TradeError(f"Position {ticket} not found", 404)

    position = positions[0]
    volume = close_volume if close_volume else position.volume

    if volume > position.volume:
        raise TradeError("Close volume exceeds position volume")

    if position.type == mt5.POSITION_TYPE_BUY:
        tick = await loop.run_in_executor(None, mt5.symbol_info_tick, position.symbol)
        price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL
    else:
        tick = await loop.run_in_executor(None, mt5.symbol_info_tick, position.symbol)
        price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY

    symbol_info = await loop.run_in_executor(None, mt5.symbol_info, position.symbol)
    filling_mode = symbol_info.filling_mode if symbol_info else 2

    if filling_mode & 1:
        type_filling = mt5.ORDER_FILLING_FOK
    elif filling_mode & 2:
        type_filling = mt5.ORDER_FILLING_IOC
    else:
        type_filling = mt5.ORDER_FILLING_RETURN

    request = {
        "action": TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": volume,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": 0,
        "comment": "[IMPULSE_V2]",
        "type_time": getattr(mt5, 'ORDER_TIME_GTC', 0),
        "type_filling": type_filling,
    }

    result = await loop.run_in_executor(None, mt5.order_send, request)
    if result is None or result.retcode != getattr(mt5, 'TRADE_RETCODE_DONE', 10009):
        detail = result.comment if result else "Unknown error"
        raise TradeError(f"Close failed: {detail}")

    close_profit = None
    close_deal_price = None
    try:
        hist_from = datetime.now() - timedelta(seconds=10)
        hist_to = datetime.now() + timedelta(seconds=1)
        deals = await loop.run_in_executor(
            None, lambda: mt5.history_deals_get(hist_from, hist_to)
        )
        if deals:
            for d in deals:
                if d.position_id == ticket:
                    close_profit = d.profit
                    close_deal_price = d.price
                    break
    except Exception:
        pass

    try:
        async with AsyncSessionLocal() as db:
            rec = await db.execute(
                select(TradeRecord).where(TradeRecord.mt5_ticket == ticket)
            )
            trade_rec = rec.scalar_one_or_none()
            if trade_rec:
                trade_rec.status = "closed"
                trade_rec.closed_at = datetime.now(timezone.utc)
                trade_rec.exit_price = close_deal_price if close_deal_price else price
                trade_rec.profit_loss = close_profit

            db.add(PositionAudit(
                user_id=user_id,
                mt5_ticket=ticket,
                action="close",
                symbol=position.symbol,
                original_sl=position.sl,
                original_tp=position.tp,
                close_volume=volume,
                close_price=price,
            ))
            await db.commit()
    except Exception:
        logger.warning(f"Close audit failed for ticket {ticket}:\n{traceback.format_exc()}")

    return {
        "success": True,
        "ticket": ticket,
        "closed_volume": volume,
        "close_price": price,
        "comment": result.comment,
    }


async def modify_position(ticket: int, new_sl: Optional[float], new_tp: Optional[float], user_id: Optional[int]) -> dict:
    await init_mt5()
    mt5 = _get_mt5()
    loop = asyncio.get_running_loop()

    positions = await loop.run_in_executor(None, lambda: mt5.positions_get(ticket=ticket))
    if positions is None or len(positions) == 0:
        raise TradeError(f"Position {ticket} not found", 404)

    position = positions[0]
    symbol_info = await loop.run_in_executor(None, mt5.symbol_info, position.symbol)
    if symbol_info is None:
        raise TradeError("Cannot get symbol info")

    digits = symbol_info.digits
    resolved_sl = round(new_sl, digits) if new_sl is not None else position.sl
    resolved_tp = round(new_tp, digits) if new_tp is not None else position.tp

    request = {
        "action": TRADE_ACTION_SLTP,
        "symbol": position.symbol,
        "position": ticket,
        "sl": resolved_sl,
        "tp": resolved_tp,
    }

    result = await loop.run_in_executor(None, mt5.order_send, request)
    if result is None or result.retcode != getattr(mt5, 'TRADE_RETCODE_DONE', 10009):
        detail = result.comment if result else "Unknown error"
        raise TradeError(f"Modify failed: {detail}")

    try:
        async with AsyncSessionLocal() as db:
            db.add(PositionAudit(
                user_id=user_id,
                mt5_ticket=ticket,
                action="modify",
                symbol=position.symbol,
                original_sl=position.sl,
                original_tp=position.tp,
                new_sl=resolved_sl,
                new_tp=resolved_tp,
            ))
            await db.commit()
    except Exception:
        logger.warning(f"PositionAudit modify failed for ticket {ticket}:\n{traceback.format_exc()}")

    return {
        "success": True,
        "ticket": ticket,
        "sl": resolved_sl,
        "tp": resolved_tp,
        "comment": result.comment,
    }
