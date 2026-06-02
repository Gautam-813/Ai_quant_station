from pathlib import Path
from typing import Tuple


def get_parquet_path(parquet_dir: Path, symbol: str, year: int) -> Path:
    fp = parquet_dir / f"{symbol}_{year}.parquet"
    if not fp.exists():
        raise FileNotFoundError(f"Parquet file not found: {fp}")
    return fp


def get_test_range(symbol: str) -> Tuple[str, str]:
    ranges = {
        "XAUUSD": ("2026-01-01", "2026-02-01"),
        "EURUSD": ("2025-06-01", "2025-07-01"),
        "GBPUSD": ("2025-06-01", "2025-07-01"),
        "BTCUSD": ("2025-06-01", "2025-07-01"),
    }
    return ranges.get(symbol, ("2025-06-01", "2025-07-01"))
