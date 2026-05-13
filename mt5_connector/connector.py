# MT5 Connector Service
# This runs on Windows server with MT5 terminal installed

import asyncio
import sys
import os
from datetime import datetime, timedelta
from typing import Optional
import MetaTrader5 as mt5

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="MT5 Connector Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# MT5 Connection State
mt5_initialized = False
last_error = None


class OrderRequest(BaseModel):
    symbol: str
    action: str
    volume: float
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    comment: str = "[IMPULSE_CONNECTOR]"
    magic: int = 0


class CloseRequest(BaseModel):
    ticket: int
    volume: Optional[float] = None


class ModifyRequest(BaseModel):
    ticket: int
    sl: Optional[float] = None
    tp: Optional[float] = None


@app.get("/")
async def root():
    return {
        "service": "MT5 Connector",
        "version": "1.0.0",
        "mt5_initialized": mt5_initialized,
        "last_error": last_error,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy" if mt5_initialized else "not_initialized",
        "mt5_connected": mt5_initialized
    }


@app.post("/initialize")
async def initialize_mt5(terminal_path: Optional[str] = None):
    """Initialize MT5 connection."""
    global mt5_initialized, last_error
    
    try:
        if terminal_path:
            if not mt5.initialize(path=terminal_path):
                last_error = mt5.last_error()
                raise HTTPException(status_code=500, detail=f"MT5 init failed: {last_error}")
        else:
            if not mt5.initialize():
                last_error = mt5.last_error()
                raise HTTPException(status_code=500, detail=f"MT5 init failed: {last_error}")
        
        mt5_initialized = True
        account = mt5.account_info()
        
        return {
            "success": True,
            "message": "MT5 initialized successfully",
            "account": {
                "login": account.login,
                "server": account.server,
                "balance": account.balance,
                "equity": account.equity
            }
        }
    except Exception as e:
        last_error = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/shutdown")
async def shutdown_mt5():
    """Shutdown MT5 connection."""
    global mt5_initialized
    mt5.shutdown()
    mt5_initialized = False
    return {"success": True, "message": "MT5 shutdown"}


@app.get("/account")
async def get_account():
    """Get account info."""
    if not mt5_initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    acc = mt5.account_info()
    if acc is None:
        raise HTTPException(status_code=500, detail="Cannot get account info")
    
    margin_level = (acc.equity / acc.margin * 100) if acc.margin > 0 else 0
    
    return {
        "login": acc.login,
        "server": acc.server,
        "name": acc.name,
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.margin_free,
        "margin_level": round(margin_level, 2),
        "profit": acc.profit,
        "currency": acc.currency,
        "leverage": acc.leverage
    }


@app.get("/symbols")
async def get_symbols():
    """Get all available symbols."""
    if not mt5_initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    symbols = mt5.symbols_get()
    if not symbols:
        return {"count": 0, "symbols": []}
    
    result = []
    for s in symbols:
        tick = mt5.symbol_info_tick(s.name)
        result.append({
            "name": s.name,
            "description": s.description,
            "visible": s.visible,
            "ask": tick.ask if tick else None,
            "bid": tick.bid if tick else None,
            "point": s.point,
            "digits": s.digits,
            "volume_min": s.volume_min,
            "volume_max": s.volume_max
        })
    
    return {"count": len(result), "symbols": result}


@app.get("/symbol/{symbol}")
async def get_symbol(symbol: str):
    """Get specific symbol info."""
    if not mt5_initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    info = mt5.symbol_info(symbol)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    
    tick = mt5.symbol_info_tick(symbol)
    
    return {
        "name": info.name,
        "description": info.description,
        "visible": info.visible,
        "ask": tick.ask if tick else None,
        "bid": tick.bid if tick else None,
        "point": info.point,
        "digits": info.digits,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max
    }


@app.post("/order")
async def place_order(order: OrderRequest):
    """Place an order."""
    if not mt5_initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    if not mt5.symbol_select(order.symbol, True):
        raise HTTPException(status_code=404, detail=f"Symbol {order.symbol} not found")
    
    symbol_info = mt5.symbol_info(order.symbol)
    tick = mt5.symbol_info_tick(order.symbol)
    
    if symbol_info is None or tick is None:
        raise HTTPException(status_code=400, detail="Broker data unavailable")
    
    if order.volume < symbol_info.volume_min:
        raise HTTPException(status_code=400, detail=f"Volume below minimum {symbol_info.volume_min}")
    
    volume = round(order.volume / symbol_info.volume_step) * symbol_info.volume_step
    volume = round(volume, 2)
    
    digits = symbol_info.digits
    point = symbol_info.point
    
    action_map = {
        "BUY": mt5.ORDER_TYPE_BUY,
        "SELL": mt5.ORDER_TYPE_SELL,
        "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
        "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
        "BUY_STOP": mt5.ORDER_TYPE_BUY_STOP,
        "SELL_STOP": mt5.ORDER_TYPE_SELL_STOP,
    }
    
    if order.action not in action_map:
        raise HTTPException(status_code=400, detail=f"Invalid action: {order.action}")
    
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
        raise HTTPException(status_code=500, detail="Cannot get price")
    
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
    
    filling_mode = symbol_info.filling_mode
    if filling_mode & 1:
        type_filling = mt5.ORDER_FILLING_FOK
    elif filling_mode & 2:
        type_filling = mt5.ORDER_FILLING_IOC
    else:
        type_filling = mt5.ORDER_FILLING_RETURN
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL if not is_pending else mt5.TRADE_ACTION_PENDING,
        "symbol": order.symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": 20,
        "magic": order.magic,
        "comment": order.comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": type_filling,
    }
    
    if sl is not None:
        request["sl"] = sl
    if tp is not None:
        request["tp"] = tp
    
    result = mt5.order_send(request)
    
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(status_code=400, detail=f"Order failed: {result.comment if result else 'Unknown'}")
    
    return {
        "success": True,
        "ticket": result.order,
        "symbol": order.symbol,
        "volume": volume,
        "price": price,
        "sl": sl,
        "tp": tp,
        "comment": result.comment,
        "position": result.order # Default to order if position not available immediately
    }


@app.post("/close")
async def close_position(close_req: CloseRequest):
    """Close a position."""
    if not mt5_initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    positions = mt5.positions_get(ticket=close_req.ticket)
    if positions is None or len(positions) == 0:
        raise HTTPException(status_code=404, detail=f"Position {close_req.ticket} not found")
    
    position = positions[0]
    close_volume = close_req.volume if close_req.volume else position.volume
    
    if close_volume > position.volume:
        raise HTTPException(status_code=400, detail="Close volume exceeds position")
    
    if position.type == mt5.POSITION_TYPE_BUY:
        price = mt5.symbol_info_tick(position.symbol).bid
        order_type = mt5.ORDER_TYPE_SELL
    else:
        price = mt5.symbol_info_tick(position.symbol).ask
        order_type = mt5.ORDER_TYPE_BUY
    
    symbol_info = mt5.symbol_info(position.symbol)
    filling_mode = symbol_info.filling_mode if symbol_info else 2
    
    if filling_mode & 1:
        type_filling = mt5.ORDER_FILLING_FOK
    elif filling_mode & 2:
        type_filling = mt5.ORDER_FILLING_IOC
    else:
        type_filling = mt5.ORDER_FILLING_RETURN
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": close_volume,
        "type": order_type,
        "position": close_req.ticket,
        "price": price,
        "deviation": 20,
        "magic": 0,
        "comment": "[IMPULSE_CONNECTOR]",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": type_filling,
    }
    
    result = mt5.order_send(request)
    
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(status_code=400, detail=f"Close failed: {result.comment if result else 'Unknown'}")
    
    return {
        "success": True,
        "ticket": close_req.ticket,
        "closed_volume": close_volume,
        "close_price": price,
        "comment": result.comment
    }


@app.post("/modify")
async def modify_position(mod_req: ModifyRequest):
    """Modify SL/TP of a position."""
    if not mt5_initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    positions = mt5.positions_get(ticket=mod_req.ticket)
    if positions is None or len(positions) == 0:
        raise HTTPException(status_code=404, detail=f"Position {mod_req.ticket} not found")
    
    position = positions[0]
    symbol_info = mt5.symbol_info(position.symbol)
    
    if symbol_info is None:
        raise HTTPException(status_code=400, detail="Cannot get symbol info")
    
    digits = symbol_info.digits
    new_sl = round(mod_req.sl, digits) if mod_req.sl is not None else position.sl
    new_tp = round(mod_req.tp, digits) if mod_req.tp is not None else position.tp
    
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": position.symbol,
        "position": mod_req.ticket,
        "sl": new_sl,
        "tp": new_tp,
    }
    
    result = mt5.order_send(request)
    
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(status_code=400, detail=f"Modify failed: {result.comment if result else 'Unknown'}")
    
    return {
        "success": True,
        "ticket": mod_req.ticket,
        "sl": new_sl,
        "tp": new_tp
    }


@app.get("/positions")
async def get_positions():
    """Get all open positions."""
    if not mt5_initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    acc = mt5.account_info()
    positions = mt5.positions_get()
    
    position_list = []
    total_profit = 0.0
    
    if positions:
        for pos in positions:
            position_list.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "direction": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume": pos.volume,
                "entry_price": pos.price_open,
                "current_price": pos.price_current,
                "tp": pos.tp if pos.tp != 0 else None,
                "position_id": pos.ticket,
                "profit": pos.profit,
                "open_time": datetime.fromtimestamp(pos.time).strftime('%Y-%m-%d %H:%M:%S')
            })
            total_profit += pos.profit
    
    margin_level = (acc.equity / acc.margin * 100) if acc.margin > 0 else 0
    
    return {
        "success": True,
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.margin_free,
        "margin_level": round(margin_level, 2),
        "open_count": len(position_list),
        "total_profit": round(total_profit, 2),
        "positions": position_list
    }


@app.get("/history")
async def get_history(hours: int = 0):
    """Get trade history."""
    if not mt5_initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    if hours > 0:
        from_time = datetime.now() - timedelta(hours=hours)
    else:
        from_time = datetime(2000, 1, 1)
    
    to_time = datetime.now() + timedelta(days=5)
    
    deals = mt5.history_deals_get(from_time, to_time)
    if deals is None:
        return {"success": True, "count": 0, "deals": []}
    
    deal_list = []
    for deal in deals:
        if deal.entry == 0 or deal.entry >= 4:
            continue
        
        deal_list.append({
            "ticket": deal.order,
            "symbol": deal.symbol,
            "direction": "BUY" if deal.type == mt5.DEAL_TYPE_BUY else "SELL",
            "volume": deal.volume,
            "price": deal.price,
            "profit": deal.profit,
            "swap": deal.swap,
            "commission": deal.commission,
            "comment": deal.comment or "",
            "position_id": deal.position_id,
            "time": datetime.utcfromtimestamp(deal.time).strftime('%Y-%m-%d %H:%M:%S'),
            "entry": "CLOSE" if deal.entry == 1 else "OPEN"
        })
    
    return {"success": True, "count": len(deal_list), "deals": deal_list}


@app.get("/data/latest/{symbol}")
async def get_latest_data(symbol: str, timeframe: str = "1h", count: int = 500):
    """Get latest OHLC data."""
    if not mt5_initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    timeframe_map = {
        '1m': mt5.TIMEFRAME_M1,
        '5m': mt5.TIMEFRAME_M5,
        '15m': mt5.TIMEFRAME_M15,
        '30m': mt5.TIMEFRAME_M30,
        '1h': mt5.TIMEFRAME_H1,
        '4h': mt5.TIMEFRAME_H4,
        '1d': mt5.TIMEFRAME_D1,
        '1w': mt5.TIMEFRAME_W1,
        '1M': mt5.TIMEFRAME_MN1
    }
    
    tf = timeframe_map.get(timeframe, mt5.TIMEFRAME_H1)
    
    if not mt5.symbol_select(symbol, True):
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        raise HTTPException(status_code=500, detail="No data available")
    
    import pandas as pd
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    data = []
    for _, row in df.iterrows():
        data.append({
            "time": row['time'].strftime('%Y-%m-%d %H:%M:%S'),
            "open": row['open'],
            "high": row['high'],
            "low": row['low'],
            "close": row['close'],
            "tick_volume": row['tick_volume']
        })
    
    return {
        "success": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(data),
        "data": data
    }


if __name__ == "__main__":
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="MT5 Connector Service")
    parser.add_argument(
        "--port", 
        type=int, 
        default=None,
        help="Port number for the service (default: 5001)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host address (default: 0.0.0.0)"
    )
    args = parser.parse_args()
    
    # Get port from environment variable or command line
    port = args.port or int(os.environ.get("MT5_CONNECTOR_PORT", 0))
    host = os.environ.get("MT5_CONNECTOR_HOST", args.host)
    
    print("=" * 60)
    print("MT5 Connector Service")
    print("=" * 60)
    print("This service connects to MetaTrader 5 and exposes")
    print("REST API for the main backend to use.")
    print("")
    
    # Interactive port selection
    if port == 0:
        print("Available port options:")
        print("  - Press Enter for default (5001)")
        print("  - Enter custom port (e.g., 5002, 8080)")
        print("")
        user_port = input("Enter port number [default: 5001]: ").strip()
        if user_port == "":
            port = 5001
        else:
            try:
                port = int(user_port)
                if port < 1 or port > 65535:
                    print("Invalid port. Using default 5001")
                    port = 5001
            except ValueError:
                print("Invalid number. Using default 5001")
                port = 5001
    
    print("")
    print(f"Starting service on http://{host}:{port}...")
    print("=" * 60)
    print("")
    print("Service will be available at:")
    print(f"  - Local:   http://localhost:{port}")
    print(f"  - Network: http://{host}:{port}")
    print("")
    print("API Endpoints:")
    print(f"  - GET  http://{host}:{port}/")
    print(f"  - GET  http://{host}:{port}/health")
    print(f"  - POST http://{host}:{port}/initialize")
    print(f"  - POST http://{host}:{port}/order")
    print("=" * 60)
    
    uvicorn.run(app, host=host, port=port, log_level="info")