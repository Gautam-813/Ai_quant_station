from fastapi import APIRouter, Depends, HTTPException, Header, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Annotated, List
from datetime import datetime, timedelta
import pytz

from ..core.config import settings
from ..core.security import get_current_user
from ..core.mt5_connector import connector_client
from ..models.schemas import (
    MT5SymbolsResponse, MT5Symbol, DataResponse, OHLCData,
    AccountInfo, PositionsResponse, Position, HistoryResponse, Trade, OHLCData
)
from ..core.database import get_db
from ..models.market_data import MarketData
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy import select

router = APIRouter(prefix="/mt5", tags=["MT5"])

# MT5 Connection State
_mt5_initialized = False
_mt5_terminal_path = None
_mt5_connector_url: str | None = None


def _get_mt5():
    """Lazy import MT5 (Windows only)."""
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        return None


def _is_using_connector() -> bool:
    """Check if we're using external connector."""
    return _mt5_connector_url is not None


def get_mt5_connector_config(
    x_mt5_connector_url: Annotated[str | None, Header()] = None
):
    """Dependency to set global connector URL from header."""
    global _mt5_connector_url
    if x_mt5_connector_url:
        _mt5_connector_url = x_mt5_connector_url
        connector_client.base_url = x_mt5_connector_url
    else:
        _mt5_connector_url = None
    return _mt5_connector_url


def verify_mt5_token(
    x_mt5_token: Annotated[str, Header()],
    connector_url: str | None = Depends(get_mt5_connector_config)
):
    """Verify MT5 API token."""
    if x_mt5_token != settings.MT5_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid MT5 token")
    return x_mt5_token


async def _cache_market_data(db: AsyncSession, symbol: str, timeframe: str, data: List[OHLCData], source: str = "mt5"):
    """Helper to cache market data in SQLite using INSERT OR IGNORE."""
    try:
        # Prepare records
        records = []
        for d in data:
            # Convert string time or datetime to datetime object for DB
            if isinstance(d.time, str):
                try:
                    dt_time = datetime.strptime(d.time, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    # Try ISO format if standard format fails
                    dt_time = datetime.fromisoformat(d.time.replace('Z', '+00:00'))
            else:
                dt_time = d.time
            
            records.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "time": dt_time,
                "open": d.open,
                "high": d.high,
                "low": d.low,
                "close": d.close,
                "tick_volume": d.tick_volume,
                "source": source
            })

        if not records:
            return

        # Use SQLite's ON CONFLICT DO NOTHING
        stmt = sqlite_insert(MarketData).values(records)
        stmt = stmt.on_conflict_do_nothing(constraint="ix_market_data_symbol_tf_time")
        
        await db.execute(stmt)
        await db.commit()
    except Exception as e:
        print(f"Error caching market data: {e}")
        # Don't fail the request just because caching failed
        pass


async def _init_mt5():
    """Initialize MT5 if not already initialized."""
    global _mt5_initialized, _mt5_terminal_path, _mt5_connector_url

    if _mt5_initialized:
        return True

    try:
        mt5 = _get_mt5()
        
        # Check if using external connector
        if _mt5_connector_url:
            # For external connector, we don't directly initialize MT5
            # The connector handles MT5 communication
            # Just mark as initialized for now (connector handles the actual MT5)
            print(f"Using external MT5 connector: {_mt5_connector_url}")
            _mt5_initialized = True
            return True
        
        # Direct MT5 initialization
        if settings.MT5_TERMINAL_PATH:
            if not mt5.initialize(path=settings.MT5_TERMINAL_PATH):
                return False
        else:
            if not mt5.initialize():
                return False
        _mt5_initialized = True
        return True
    except Exception as e:
        print(f"MT5 initialization error: {e}")
        return False


@router.get("/health")
async def health_check(token: str = Depends(verify_mt5_token)):
    """Check MT5 server health."""
    if _is_using_connector():
        try:
            result = await connector_client.health()
            return {
                "status": "running",
                "connector": _mt5_connector_url,
                "mt5_initialized": result.get("mt5_initialized", False),
                "server": _mt5_connector_url
            }
        except Exception as e:
            error_msg = f"Connector unavailable at {_mt5_connector_url}: {str(e)}"
            print(error_msg)
            raise HTTPException(status_code=503, detail=error_msg)
    
    initialized = await _init_mt5()
    return {
        "status": "running",
        "mt5_initialized": initialized,
        "server": settings.MT5_SERVER_PORT
    }


@router.post("/initialize")
async def initialize_mt5(
    terminal_path: Optional[str] = None,
    token: str = Depends(verify_mt5_token)
):
    """Initialize MT5 connection."""
    global _mt5_initialized, _mt5_terminal_path

    try:
        mt5 = _get_mt5()
        if terminal_path:
            if not mt5.initialize(path=terminal_path):
                raise HTTPException(status_code=500, detail="Failed to initialize MT5")
            _mt5_terminal_path = terminal_path
        else:
            if not mt5.initialize():
                raise HTTPException(status_code=500, detail="Failed to initialize MT5")

        _mt5_initialized = True
        account = mt5.account_info()

        return {
            "success": True,
            "message": "MT5 initialized successfully",
            "account": account.login if account else None,
            "server": account.server if account else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols/all")
async def get_all_symbols(token: str = Depends(verify_mt5_token)):
    """Get all available symbols from broker."""
    if not await _init_mt5():
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    mt5 = _get_mt5()
    all_symbols = mt5.symbols_get()
    if not all_symbols:
        return {"count": 0, "symbols": []}

    symbols = []
    for s in all_symbols:
        tick = mt5.symbol_info_tick(s.name)
        symbols.append(MT5Symbol(
            name=s.name,
            description=s.description,
            visible=s.visible,
            ask=tick.ask if tick else None,
            bid=tick.bid if tick else None,
            point=s.point,
            digits=s.digits,
            volume_min=s.volume_min,
            volume_max=s.volume_max
        ))

    return MT5SymbolsResponse(count=len(symbols), symbols=symbols)


@router.get("/symbols")
async def get_symbols_jwt(
    current_user: dict = Depends(get_current_user),
    connector_url: str | None = Depends(get_mt5_connector_config)
):
    """Get available symbols from MT5 (JWT auth)."""
    if not await _init_mt5():
        return {"success": False, "symbols": [], "error": "MT5 not available"}

    if _is_using_connector():
        try:
            res = await connector_client.get_symbols()
            all_symbols = res.get("symbols", [])
            symbols = []
            seen = set()
            for s in all_symbols:
                name = s.get("name")
                # Only include symbols that are visible in the terminal
                if name and name not in seen and s.get("visible", True):
                    seen.add(name)
                    symbols.append({"symbol": name, "name": name, "type": "forex"})
            return {"success": True, "symbols": symbols}
        except Exception as e:
            return {"success": False, "symbols": [], "error": str(e)}

    mt5 = _get_mt5()
    all_symbols = mt5.symbols_get()
    if not all_symbols:
        return {"success": True, "symbols": []}

    symbols = []
    seen = set()
    for s in all_symbols:
        if s.visible and s.name not in seen:
            seen.add(s.name)
            symbols.append({"symbol": s.name, "name": s.name, "type": "forex"})

    return {"success": True, "symbols": symbols}


@router.get("/symbol/{symbol}")
async def get_symbol_info(symbol: str, token: str = Depends(verify_mt5_token)):
    """Get detailed symbol information."""
    if not await _init_mt5():
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    mt5 = _get_mt5()
    info = mt5.symbol_info(symbol)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

    tick = mt5.symbol_info_tick(symbol)

    return MT5Symbol(
        name=info.name,
        description=info.description,
        visible=info.visible,
        ask=tick.ask if tick else None,
        bid=tick.bid if tick else None,
        point=info.point,
        digits=info.digits,
        volume_min=info.volume_min,
        volume_max=info.volume_max
    )


@router.post("/data/fetch")
async def fetch_data(
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    token: str = Depends(verify_mt5_token),
    db: AsyncSession = Depends(get_db)
):
    """Fetch OHLC data."""
    if not await _init_mt5():
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    mt5 = _get_mt5()

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

    tf = timeframe_map.get(timeframe, mt5.TIMEFRAME_M1)

    timezone = pytz.timezone("Etc/UTC")
    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

    if start_dt.tzinfo is None:
        start_dt = timezone.localize(start_dt)
    if end_dt.tzinfo is None:
        end_dt = timezone.localize(end_dt)

    if not mt5.symbol_select(symbol, True):
        raise HTTPException(status_code=404, detail=f"Failed to select symbol: {symbol}")

    rates = mt5.copy_rates_range(symbol, tf, start_dt, end_dt)
    if rates is None or len(rates) == 0:
        raise HTTPException(status_code=500, detail="No data available")

    import pandas as pd
    df = pd.DataFrame(rates)

    ohlc_data = []
    for _, row in df.iterrows():
        ohlc_data.append(OHLCData(
            time=int(row['time']),  # Unix timestamp - MT5 time directly
            open=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
            tick_volume=row['tick_volume'],
            spread=row.get('spread', 0),
            real_volume=row.get('real_volume', 0)
        ))

    # Cache the data
    await _cache_market_data(db, symbol, timeframe, ohlc_data, source="mt5")

    return DataResponse(
        success=True,
        symbol=symbol,
        timeframe=timeframe,
        rows=len(ohlc_data),
        data=ohlc_data
    )


class DataFetchRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    count: int = 1000


@router.post("/data/latest")
async def fetch_latest(
    request: DataFetchRequest,
    token: str = Depends(verify_mt5_token),
    db: AsyncSession = Depends(get_db)
):
    """Fetch the latest N candles."""
    if not await _init_mt5():
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    symbol = request.symbol
    timeframe = request.timeframe
    count = request.count

    if _is_using_connector():
        try:
            res = await connector_client.get_latest_data(
                symbol=request.symbol,
                timeframe=request.timeframe,
                count=request.count
            )
            if res.get("success"):
                ohlc_data = []
                for item in res.get("data", []):
                    ohlc_data.append(OHLCData(**item))
                
                # Cache the data
                await _cache_market_data(db, request.symbol, request.timeframe, ohlc_data, source="mt5_connector")

                return DataResponse(
                    success=True,
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                    rows=len(ohlc_data),
                    data=ohlc_data
                )
            else:
                raise HTTPException(status_code=500, detail=res.get("error", "Failed to fetch data from connector"))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    mt5 = _get_mt5()

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

    tf = timeframe_map.get(timeframe, mt5.TIMEFRAME_M1)

    if not mt5.symbol_select(symbol, True):
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        raise HTTPException(status_code=500, detail="No data available")

    import pandas as pd
    df = pd.DataFrame(rates)

    ohlc_data = []
    for _, row in df.iterrows():
        ohlc_data.append(OHLCData(
            time=int(row['time']),  # Unix timestamp - MT5 time directly
            open=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
            tick_volume=row['tick_volume'],
            spread=row.get('spread', 0),
            real_volume=row.get('real_volume', 0)
        ))

    # Cache the data
    await _cache_market_data(db, symbol, timeframe, ohlc_data, source="mt5")

    return DataResponse(
        success=True,
        symbol=symbol,
        timeframe=timeframe,
        rows=len(ohlc_data),
        data=ohlc_data
    )


@router.get("/account")
async def get_account_info(token: str = Depends(verify_mt5_token)):
    """Get account information."""
    if not await _init_mt5():
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    if _is_using_connector():
        try:
            res = await connector_client.get_account_info()
            if res.get("success"):
                return AccountInfo(**res.get("data", {}))
            else:
                raise HTTPException(status_code=500, detail=res.get("error", "Failed to get account info from connector"))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    mt5 = _get_mt5()
    acc = mt5.account_info()
    if acc is None:
        raise HTTPException(status_code=500, detail="Cannot get account info")

    margin_level = (acc.equity / acc.margin * 100) if acc.margin > 0 else 0

    return AccountInfo(
        login=acc.login,
        server=acc.server,
        name=acc.name,
        balance=acc.balance,
        equity=acc.equity,
        margin=acc.margin,
        free_margin=acc.margin_free,
        margin_level=round(margin_level, 2),
        profit=acc.profit,
        currency=acc.currency,
        leverage=acc.leverage
    )


@router.get("/positions")
async def get_positions(token: str = Depends(verify_mt5_token)):
    """Get open positions."""
    if not await _init_mt5():
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    if _is_using_connector():
        try:
            res = await connector_client.get_positions()
            if res.get("success"):
                data = res.get("data", {})
                positions_raw = data.get("positions", [])
                position_list = [Position(**p) for p in positions_raw]
                
                return PositionsResponse(
                    success=True,
                    balance=data.get("balance", 0.0),
                    equity=data.get("equity", 0.0),
                    margin=data.get("margin", 0.0),
                    free_margin=data.get("free_margin", 0.0),
                    margin_level=data.get("margin_level", 0.0),
                    open_count=len(position_list),
                    total_profit=data.get("total_profit", 0.0),
                    positions=position_list
                )
            else:
                raise HTTPException(status_code=500, detail=res.get("error", "Failed to get positions from connector"))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    mt5 = _get_mt5()
    acc = mt5.account_info()
    positions = mt5.positions_get()

    position_list = []
    total_profit = 0.0

    if positions:
        for pos in positions:
            position_list.append(Position(
                ticket=pos.ticket,
                symbol=pos.symbol,
                direction="BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                volume=pos.volume,
                entry_price=pos.price_open,
                current_price=pos.price_current,
                sl=pos.sl if pos.sl != 0 else None,
                tp=pos.tp if pos.tp != 0 else None,
                profit=pos.profit,
                open_time=datetime.fromtimestamp(pos.time).strftime('%Y-%m-%d %H:%M:%S')
            ))
            total_profit += pos.profit

    margin_level = (acc.equity / acc.margin * 100) if acc.margin > 0 else 0

    return PositionsResponse(
        success=True,
        balance=acc.balance,
        equity=acc.equity,
        margin=acc.margin,
        free_margin=acc.margin_free,
        margin_level=round(margin_level, 2),
        open_count=len(position_list),
        total_profit=round(total_profit, 2),
        positions=position_list
    )


@router.get("/history")
async def get_history(hours: int = 0, token: str = Depends(verify_mt5_token)):
    """Get trade history."""
    if not await _init_mt5():
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    if _is_using_connector():
        try:
            res = await connector_client.get_history(hours=hours)
            if res.get("success"):
                trades_raw = res.get("deals", [])
                trade_list = [Trade(**t) for t in trades_raw]
                return HistoryResponse(success=True, count=len(trade_list), deals=trade_list)
            else:
                raise HTTPException(status_code=500, detail=res.get("error", "Failed to get history from connector"))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    mt5 = _get_mt5()
    # ... (rest of direct MT5 logic remains the same)

    if hours > 0:
        from_time = datetime.now() - timedelta(hours=hours)
    else:
        from_time = datetime(2000, 1, 1)

    to_time = datetime.now() + timedelta(days=5)

    deals = mt5.history_deals_get(from_time, to_time)
    if deals is None:
        return HistoryResponse(success=True, count=0, deals=[])

    # Get position comments
    position_comments = {}
    for d in deals:
        if d.entry == 0 and d.comment:
            position_comments[d.position_id] = d.comment

    deal_list = []
    for deal in deals:
        if deal.entry == 0 or deal.entry >= 4:
            continue

        final_comment = deal.comment or ""
        orig_comment = position_comments.get(deal.position_id, "")
        if not final_comment:
            final_comment = orig_comment
        elif final_comment.lower() in ["[tp]", "tp", "[sl]", "sl"] and orig_comment:
            final_comment = f"{orig_comment} {final_comment}"

        deal_list.append(Trade(
            ticket=deal.order,
            symbol=deal.symbol,
            direction="BUY" if deal.type == mt5.DEAL_TYPE_BUY else "SELL",
            volume=deal.volume,
            price=deal.price,
            profit=deal.profit,
            swap=deal.swap,
            commission=deal.commission,
            comment=final_comment,
            time=datetime.utcfromtimestamp(deal.time).strftime('%Y-%m-%d %H:%M:%S'),
            entry="CLOSE" if deal.entry == 1 else "OPEN"
        ))

    return HistoryResponse(success=True, count=len(deal_list), deals=deal_list)