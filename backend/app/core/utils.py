import json
import re
import math
from typing import Optional, Any, List, Dict

def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively cleans objects for JSON serialization safety.
    Handles Datetime, Pandas, and NumPy types.
    """
    from datetime import date, time, datetime

    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, (date, time)):
        return str(obj)

    try:
        import pandas as _pd
        if isinstance(obj, _pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, _pd.Timedelta):
            return str(obj)
        try:
            if _pd.isna(obj):
                return None
        except (TypeError, ValueError):
            pass
    except ImportError:
        pass

    try:
        import numpy as _np
        if isinstance(obj, (_np.integer,)):
            return int(obj)
        if isinstance(obj, (_np.floating,)):
            v = float(obj)
            return None if math.isnan(v) or math.isinf(v) else v
        if isinstance(obj, _np.bool_):
            return bool(obj)
        if isinstance(obj, _np.ndarray):
            return sanitize_for_json(obj.tolist())
    except ImportError:
        pass

    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(i) for i in obj]
    if hasattr(obj, 'item') and callable(obj.item):
        try:
            return sanitize_for_json(obj.item())
        except Exception:
            pass
    return obj

def detect_trade_setup(text: str) -> Optional[dict]:
    """Detect TRADE_SETUP JSON from AI response."""
    # Pattern to match ```json { ... } ```
    json_pattern = r"```json\s*(.*?)\s*```"
    blocks = re.findall(json_pattern, text, re.S | re.I)

    for block in blocks:
        try:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                return data
        except json.JSONDecodeError:
            pass

    # Fallback: try to parse the entire text as JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    return None
