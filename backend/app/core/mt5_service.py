import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import MetaTrader5 as mt5
from ..core.config import settings
from ..core.mt5_connector import connector_client

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
    
    if connector_url:
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
            
        # Convert to list of dicts
        import pandas as pd
        df = pd.DataFrame(rates)
        return df.to_dict("records")
