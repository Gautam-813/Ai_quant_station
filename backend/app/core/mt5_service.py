import asyncio
import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from ..core.config import settings
from ..core.mt5_connector import connector_client

# Lazy import for MetaTrader5 — only available on Windows
_mt5 = None
def _get_mt5():
    global _mt5
    if _mt5 is None:
        try:
            import MetaTrader5 as mt5
            _mt5 = mt5
        except ImportError:
            _mt5 = False  # Sentinel: not available on this platform
    return _mt5 if _mt5 else None

logger = logging.getLogger(__name__)

# Connection State
_mt5_initialized = False

async def init_mt5_connection():
    """Initialize MT5 (Direct or Connector) and return True if successful."""
    global _mt5_initialized
    
    if _mt5_initialized:
        return True
        
    try:
        # 1. Check if we should use external connector
        connector_url = settings.MT5_CONNECTOR_URL
        if connector_url:
            logger.info(f"Using external MT5 connector: {connector_url}")
            # Connector client handles its own initialization on the remote end
            _mt5_initialized = True
            return True
            
        # 2. Direct MT5 initialization (Windows only)
        mt5 = _get_mt5()
        if mt5 is None:
            logger.warning("MetaTrader5 not available on this platform. Use MT5_CONNECTOR_URL for remote trading.")
            return False
        terminal_path = settings.MT5_TERMINAL_PATH
        if terminal_path:
            if not mt5.initialize(path=terminal_path):
                logger.error(f"MT5 failed to initialize at path: {terminal_path}")
                return False
        else:
            if not mt5.initialize():
                logger.error("MT5 failed to initialize (default path)")
                return False
                
        _mt5_initialized = True
        logger.info("Direct MT5 Connection Established.")
        return True
        
    except Exception as e:
        logger.error(f"MT5 Connection Exception: {e}")
        return False

async def fetch_ohlc_range(symbol: str, timeframe: str, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
    """Generic fetcher that abstracts direct MT5 vs Connector."""
    if not await init_mt5_connection():
        return []
        
    connector_url = settings.MT5_CONNECTOR_URL
    
    if connector_url and settings.MT5_USE_EXTERNAL_CONNECTOR:
        try:
            # Note: The connector endpoint for ranges might vary, using latest/data pattern
            res = await connector_client._request("GET", f"/data/range/{symbol}", params={
                "timeframe": timeframe,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat()
            })
            if res.get("success"):
                return res.get("data", [])
        except Exception as e:
            logger.error(f"Connector fetch error for {symbol}: {e}")
            return []
    else:
        mt5 = _get_mt5()
        # Direct MT5 mapping
        tf_map = {
            '1m': mt5.TIMEFRAME_M1,
            '5m': mt5.TIMEFRAME_M5,
            '15m': mt5.TIMEFRAME_M15,
            '30m': mt5.TIMEFRAME_M30,
            '1h': mt5.TIMEFRAME_H1,
            '4h': mt5.TIMEFRAME_H4,
            '1d': mt5.TIMEFRAME_D1,
        }
        tf = tf_map.get(timeframe, mt5.TIMEFRAME_M1)
        
        # Ensure symbol is selected
        if not mt5.symbol_select(symbol, True):
            logger.error(f"Symbol {symbol} not found in MT5.")
            return []
            
        rates = mt5.copy_rates_range(symbol, tf, start_dt, end_dt)
        if rates is None or len(rates) == 0:
            return []
            
        import pandas as pd
        df = pd.DataFrame(rates)
        # Convert broker-local timestamps to UTC if offset is configured
        offset_hours = settings.MT5_BROKER_UTC_OFFSET
        if offset_hours != 0:
            df['time'] = df['time'] - (offset_hours * 3600)
        return df.to_dict("records")


async def fetch_latest_candles(symbol: str, count: int = 5000, timeframe: str = "1m") -> List[Dict[str, Any]]:
    """Fetch the latest N candles for a symbol.

    Abstracts direct MT5 vs External Connector.
    Returns a list of dicts with keys: time, open, high, low, close, tick_volume
    or empty list on failure.
    """
    if not await init_mt5_connection():
        return []

    connector_url = settings.MT5_CONNECTOR_URL

    if connector_url and settings.MT5_USE_EXTERNAL_CONNECTOR:
        try:
            res = await connector_client.get_latest_data(symbol, timeframe, count)
            if res.get("success"):
                return res.get("data", [])
        except Exception as e:
            logger.error(f"Connector fetch_latest error for {symbol}: {e}")
            return []
    else:
        mt5 = _get_mt5()
        if mt5 is None:
            return []
        tf_map = {
            '1m': mt5.TIMEFRAME_M1, '5m': mt5.TIMEFRAME_M5, '15m': mt5.TIMEFRAME_M15,
            '30m': mt5.TIMEFRAME_M30, '1h': mt5.TIMEFRAME_H1, '4h': mt5.TIMEFRAME_H4,
            '1d': mt5.TIMEFRAME_D1, '1w': mt5.TIMEFRAME_W1, '1M': mt5.TIMEFRAME_MN1,
        }
        tf = tf_map.get(timeframe, mt5.TIMEFRAME_M1)

        if not mt5.symbol_select(symbol, True):
            logger.error(f"Symbol {symbol} not found in MT5.")
            return []

        import pandas as pd
        loop = asyncio.get_running_loop()
        rates = await loop.run_in_executor(None, mt5.copy_rates_from_pos, symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            return []

        df = pd.DataFrame(rates)
        offset_hours = settings.MT5_BROKER_UTC_OFFSET
        if offset_hours != 0:
            df['time'] = df['time'] - (offset_hours * 3600)
        records = df.to_dict("records")
        # Standardise field names to match API schema
        result = []
        for r in records:
            result.append({
                "time": int(r.get("time", 0)),
                "open": float(r.get("open", 0)),
                "high": float(r.get("high", 0)),
                "low": float(r.get("low", 0)),
                "close": float(r.get("close", 0)),
                "tick_volume": int(r.get("tick_volume", 0)),
                "spread": int(r.get("spread", 0)),
                "real_volume": int(r.get("real_volume", 0)),
            })
        return result
