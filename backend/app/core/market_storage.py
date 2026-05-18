"""
Market Data Storage - Parquet Files
Stores OHLC market data in efficient parquet format for fast loading
"""

import os
import pandas as pd
from datetime import datetime
from typing import List, Optional
from pathlib import Path


class MarketDataStorage:
    
    def __init__(self, storage_dir: str = ""):
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(__file__).resolve().parent.parent.parent.parent / "market_data"
        self.storage_dir.mkdir(exist_ok=True)
    
    def _get_parquet_path(self, symbol: str, timeframe: str) -> Path:
        """Get the parquet file path for a symbol/timeframe."""
        filename = f"{symbol}_{timeframe}.parquet"
        return self.storage_dir / filename
    
    def save_candles(self, symbol: str, timeframe: str, candles: List[dict]) -> bool:
        """Save candle data to parquet file."""
        try:
            if not candles:
                return False
            
            df = pd.DataFrame(candles)
            
            # Convert time to datetime if it's a timestamp
            if 'time' in df.columns:
                if isinstance(df['time'].iloc[0], (int, float)):
                    df['time'] = pd.to_datetime(df['time'], unit='s')
                elif isinstance(df['time'].iloc[0], str):
                    df['time'] = pd.to_datetime(df['time'])
            
            # Ensure proper column types
            numeric_cols = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['symbol'] = symbol
            df['timeframe'] = timeframe
            df['updated_at'] = datetime.utcnow()
            
            # Append to existing or create new
            parquet_path = self._get_parquet_path(symbol, timeframe)
            
            if parquet_path.exists():
                existing_df = pd.read_parquet(parquet_path)
                # Combine and remove duplicates
                df = pd.concat([existing_df, df], ignore_index=True)
                df = df.drop_duplicates(subset=['time'], keep='last')
                df = df.sort_values('time')
            
            df.to_parquet(parquet_path, index=False)
            return True
            
        except Exception as e:
            print(f"[ParquetStorage] Save error: {e}")
            return False
    
    def load_candles(self, symbol: str, timeframe: str, count: int = 1000) -> List[dict]:
        """Load candle data from parquet file."""
        try:
            parquet_path = self._get_parquet_path(symbol, timeframe)
            
            if not parquet_path.exists():
                return []
            
            df = pd.read_parquet(parquet_path)
            
            # Get last 'count' candles
            if len(df) > count:
                df = df.tail(count)
            
            # Convert to list of dicts
            result = df.to_dict('records')
            
            # Convert time back to unix timestamp
            for r in result:
                if isinstance(r['time'], pd.Timestamp):
                    r['time'] = int(r['time'].timestamp())
                elif isinstance(r['time'], datetime):
                    r['time'] = int(r['time'].timestamp())
            
            return result
            
        except Exception as e:
            print(f"[ParquetStorage] Load error: {e}")
            return []
    
    def get_latest(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Get the latest candle for a symbol/timeframe."""
        candles = self.load_candles(symbol, timeframe, count=1)
        return candles[-1] if candles else None
    
    def get_symbols(self) -> List[str]:
        """Get list of symbols in storage."""
        try:
            files = list(self.storage_dir.glob("*.parquet"))
            symbols = set()
            for f in files:
                # Extract symbol from filename (e.g., EURUSD_1h.parquet)
                name = f.stem
                if '_' in name:
                    symbol = name.rsplit('_', 1)[0]
                    symbols.add(symbol)
            return sorted(list(symbols))
        except Exception as e:
            print(f"[ParquetStorage] Get symbols error: {e}")
            return []


# Global instance
market_storage = MarketDataStorage()