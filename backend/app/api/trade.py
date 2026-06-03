import asyncio
from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional, Annotated
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from ..core.config import settings
from ..core.security import decode_token
from ..core.database import AsyncSessionLocal
from ..models.schemas import OrderRequest, OrderResponse, CloseRequest, ModifyRequest
from ..models.ai_memory import TradeRecord, PositionAudit

_security = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/trade", tags=["Trading"])


def _get_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        return None


async def verify_mt5_token(
    x_mt5_token: Annotated[Optional[str], Header()] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
):
    if x_mt5_token:
        if x_mt5_token == settings.MT5_API_TOKEN:
            return {"auth_method": "mt5_token", "user_id": None}
        raise HTTPException(status_code=401, detail="Invalid MT5 token")
    if credentials:
        payload = await decode_token(credentials.credentials)
        if payload and payload.get("type") == "access":
            return {"auth_method": "jwt", "user": payload.get("sub"), "user_id": payload.get("user_id")}
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Missing authentication: provide x-mt5-token header or Authorization Bearer token"
    )


async def _init_mt5():
    mt5 = _get_mt5()
    if mt5 is None:
        return False
    
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, mt5.initialize)
    return ok


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


@router.post("/order", response_model=OrderResponse)
async def place_order(order: OrderRequest, token: str = Depends(verify_mt5_token)):
    """Place a market or pending order."""
    if not await _init_mt5():
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    mt5 = _get_mt5()
    loop = asyncio.get_running_loop()

    if not await loop.run_in_executor(None, mt5.symbol_select, order.symbol, True):
        raise HTTPException(status_code=404, detail=f"Symbol {order.symbol} not found")

    symbol_info = await loop.run_in_executor(None, mt5.symbol_info, order.symbol)
    tick = await loop.run_in_executor(None, mt5.symbol_info_tick, order.symbol)

    if symbol_info is None or tick is None:
        raise HTTPException(status_code=400, detail=f"Broker data unavailable for {order.symbol}")

    if order.volume < symbol_info.volume_min:
        raise HTTPException(
            status_code=400,
            detail=f"Volume {order.volume} below minimum {symbol_info.volume_min}"
        )

    volume = round(order.volume / symbol_info.volume_step) * symbol_info.volume_step
    volume = round(volume, 2)

    point = symbol_info.point
    digits = symbol_info.digits

    action_map = {
        "BUY": ORDER_TYPE_BUY,
        "SELL": ORDER_TYPE_SELL,
        "BUY_LIMIT": getattr(mt5, 'ORDER_TYPE_BUY_LIMIT', 2),
        "SELL_LIMIT": getattr(mt5, 'ORDER_TYPE_SELL_LIMIT', 3),
        "BUY_STOP": getattr(mt5, 'ORDER_TYPE_BUY_STOP', 4),
        "SELL_STOP": getattr(mt5, 'ORDER_TYPE_SELL_STOP', 5),
    }

    if order.action not in action_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action: {order.action}"
        )

    order_type = action_map[order.action]
    is_pending = order.action in ("BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP")

    if is_pending and order.price is None:
        raise HTTPException(status_code=400, detail="Price required for pending orders")

    if is_pending:
        price = order.price
    elif order.action == "BUY":
        price = tick.ask
    else:
        price = tick.bid

    if price is None:
        raise HTTPException(status_code=500, detail="Cannot get current price")

    price = round(price, digits)

    # Validate SL/TP
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
        "type_time": getattr(mt5, 'ORDER_TIME_GTC', 0),
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
        raise HTTPException(status_code=400, detail=f"Order failed: {result.comment if result else 'Unknown'}")

    # Save to trade_records for audit trail
    try:
        async with AsyncSessionLocal() as db:
            trade_rec = TradeRecord(
                user_id=token.get("user_id") or 0,
                symbol=order.symbol, direction="BUY" if "BUY" in order.action else "SELL",
                entry_price=price, stop_loss=sl, take_profit=tp,
                volume=volume, order_type="market" if not is_pending else "pending",
                status="open", mt5_ticket=result.order,
                executed_at=datetime.now(timezone.utc), comment=order.comment,
                ai_message=str(order.chat_memory_id) if order.chat_memory_id else None,
            )
            db.add(trade_rec)
            await db.commit()
    except Exception:
        import traceback as _tb
        print(f"WARNING: Failed to save trade record for ticket {result.order}:\n{_tb.format_exc()}")
        # Order still succeeds — don't fail MT5 order if audit trail save fails

    return OrderResponse(
        success=True,
        ticket=result.order,
        symbol=order.symbol,
        action=order.action,
        volume=volume,
        price=price,
        sl=sl,
        tp=tp,
        comment=result.comment
    )


@router.post("/close")
async def close_position(close_req: CloseRequest, token: str = Depends(verify_mt5_token)):
    """Close an open position."""
    if not await _init_mt5():
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    mt5 = _get_mt5()
    loop = asyncio.get_running_loop()

    # Use lambda to handle keyword arguments in run_in_executor
    positions = await loop.run_in_executor(None, lambda: mt5.positions_get(ticket=close_req.ticket))

    if positions is None or len(positions) == 0:
        raise HTTPException(status_code=404, detail=f"Position {close_req.ticket} not found")

    position = positions[0]
    close_volume = close_req.volume if close_req.volume else position.volume

    if close_volume > position.volume:
        raise HTTPException(status_code=400, detail="Close volume exceeds position volume")

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
        "volume": close_volume,
        "type": order_type,
        "position": close_req.ticket,
        "price": price,
        "deviation": 20,
        "magic": 0,
        "comment": "[IMPULSE_V2]",
        "type_time": getattr(mt5, 'ORDER_TIME_GTC', 0),
        "type_filling": type_filling,
    }

    result = await loop.run_in_executor(None, mt5.order_send, request)

    if result is None or result.retcode != getattr(mt5, 'TRADE_RETCODE_DONE', 10009):
        raise HTTPException(status_code=400, detail=f"Close failed: {result.comment if result else 'Unknown error'}")

    # Query MT5 history to get the closing deal's actual P&L and price
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
                if d.position_id == close_req.ticket:
                    close_profit = d.profit
                    close_deal_price = d.price
                    break
    except Exception:
        pass

    # Update TradeRecord with close details and write audit trail
    try:
        uid = token.get("user_id") if isinstance(token, dict) else None
        async with AsyncSessionLocal() as db:
            rec = await db.execute(
                select(TradeRecord).where(TradeRecord.mt5_ticket == close_req.ticket)
            )
            trade_rec = rec.scalar_one_or_none()
            if trade_rec:
                trade_rec.status = "closed"
                trade_rec.closed_at = datetime.now(timezone.utc)
                trade_rec.exit_price = close_deal_price if close_deal_price else price
                trade_rec.profit_loss = close_profit

            db.add(PositionAudit(
                user_id=uid, mt5_ticket=close_req.ticket,
                action="close", symbol=position.symbol,
                original_sl=position.sl, original_tp=position.tp,
                close_volume=close_volume, close_price=price,
            ))
            await db.commit()
    except Exception:
        import traceback as _tb
        print(f"[trade] Close audit failed for ticket {close_req.ticket}:\n{_tb.format_exc()}")

    return {
        "success": True,
        "ticket": close_req.ticket,
        "closed_volume": close_volume,
        "close_price": price,
        "comment": result.comment
    }


@router.post("/modify")
async def modify_position(mod_req: ModifyRequest, token: str = Depends(verify_mt5_token)):
    """Modify SL and/or TP of a position."""
    if not await _init_mt5():
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    mt5 = _get_mt5()
    loop = asyncio.get_running_loop()

    # Use lambda to handle keyword arguments in run_in_executor
    positions = await loop.run_in_executor(None, lambda: mt5.positions_get(ticket=mod_req.ticket))
    
    if positions is None or len(positions) == 0:
        raise HTTPException(status_code=404, detail=f"Position {mod_req.ticket} not found")

    position = positions[0]
    symbol_info = await loop.run_in_executor(None, mt5.symbol_info, position.symbol)

    if symbol_info is None:
        raise HTTPException(status_code=400, detail="Cannot get symbol info")

    digits = symbol_info.digits
    new_sl = round(mod_req.sl, digits) if mod_req.sl is not None else position.sl
    new_tp = round(mod_req.tp, digits) if mod_req.tp is not None else position.tp

    request = {
        "action": TRADE_ACTION_SLTP,
        "symbol": position.symbol,
        "position": mod_req.ticket,
        "sl": new_sl,
        "tp": new_tp,
    }

    result = await loop.run_in_executor(None, mt5.order_send, request)

    if result is None or result.retcode != getattr(mt5, 'TRADE_RETCODE_DONE', 10009):
        raise HTTPException(status_code=400, detail=f"Modify failed: {result.comment if result else 'Unknown error'}")

    # Write audit trail
    try:
        uid = token.get("user_id") if isinstance(token, dict) else None
        async with AsyncSessionLocal() as db:
            db.add(PositionAudit(
                user_id=uid, mt5_ticket=mod_req.ticket,
                action="modify", symbol=position.symbol,
                original_sl=position.sl, original_tp=position.tp,
                new_sl=new_sl, new_tp=new_tp,
            ))
            await db.commit()
    except Exception:
        import traceback as _tb
        print(f"[trade] PositionAudit modify failed for ticket {mod_req.ticket}:\n{_tb.format_exc()}")

    return {
        "success": True,
        "ticket": mod_req.ticket,
        "sl": new_sl,
        "tp": new_tp,
        "comment": result.comment
    }