"""
Code Execution Endpoint
Executes Python code safely with market data and returns charts + tables
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import io
import contextlib
import traceback
import math
import json
import base64

router = APIRouter(prefix="/execute", tags=["AI"])


class ExecuteCodeRequest(BaseModel):
    code: str
    market_data: Optional[List[Dict[str, Any]]] = None
    symbol: Optional[str] = None


class ExecuteCodeResponse(BaseModel):
    success: bool
    output: str = ""
    error: Optional[str] = None
    data_preview: Optional[str] = None
    charts: Optional[List[Dict[str, Any]]] = None
    tables: Optional[List[Dict[str, Any]]] = None


@router.post("/code", response_model=ExecuteCodeResponse)
async def execute_code(request: ExecuteCodeRequest):
    """Execute Python code with market data (df) and common libraries."""
    result = await run_python_code(request.code, request.market_data, request.symbol)
    return ExecuteCodeResponse(**result)


async def run_python_code(code: str, market_data: Optional[List[Dict[str, Any]]] = None, symbol: Optional[str] = None):
    """Core logic to execute Python code safely with market data."""
    # Create DataFrame from market data
    df = None
    if market_data:
        try:
            import pandas as pd
            df = pd.DataFrame(market_data)
            # Ensure numeric columns
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create DataFrame: {str(e)}"
            }

    # Charts and tables storage
    charts = []
    tables = []

    # Build execution environment with charting support - RESTRICTED builtins for security
    safe_builtins = {
        'abs': abs, 'all': all, 'any': any, 'bool': bool, 'dict': dict,
        'enumerate': enumerate, 'float': float, 'int': int, 'len': len,
        'list': list, 'max': max, 'min': min, 'range': range,
        'round': round, 'sorted': sorted, 'str': str, 'sum': sum,
        'tuple': tuple, 'type': type, 'zip': zip, 'map': map, 'filter': filter,
        'True': True, 'False': False, 'None': None,
        'isinstance': isinstance, 'hasattr': hasattr, 'getattr': getattr,
        'setattr': setattr, 'reversed': reversed, 'slice': slice,
        'iter': iter, 'next': next, 'print': print, 'Exception': Exception,
        'ValueError': ValueError, 'TypeError': TypeError, 'KeyError': KeyError,
        'IndexError': IndexError, 'ZeroDivisionError': ZeroDivisionError,
        'KeyboardInterrupt': KeyboardInterrupt,
    }
    safe_globals = {
        '__builtins__': safe_builtins,
        'pd': None,
        'np': None,
        'math': math,
        'json': json,
        'df': df,
        'symbol': symbol,
        'print': print,
        'show_chart': None,
        'show_table': None,
        '_charts': [],
        '_tables': [],
    }

    # Import commonly needed libraries
    try:
        import pandas as pd
        import numpy as np
        safe_globals['pd'] = pd
        safe_globals['np'] = np

        # Add advanced trading and math libraries
        try:
            import pandas_ta as ta
            safe_globals['ta'] = ta
        except: pass
        
        try:
            import scipy
            safe_globals['scipy'] = scipy
        except: pass
        
        try:
            from sklearn import linear_model
            safe_globals['sklearn'] = sklearn
        except: pass

        # Setup matplotlib without display
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        # Define show_chart function for code to use
        def show_chart(data, title="Chart", color="#2563eb", chart_type="line"):
            """Display a chart - stores data for frontend rendering."""
            if isinstance(data, list):
                safe_globals['_charts'].append({
                    "title": title,
                    "data": data,
                    "color": color,
                    "type": chart_type
                })
            elif hasattr(data, 'tolist'):
                safe_globals['_charts'].append({
                    "title": title,
                    "data": data.tolist(),
                    "color": color,
                    "type": chart_type
                })

        def show_table(data, title="Data"):
            """Display a table - capped at 50 rows for performance and DB stability."""
            if isinstance(data, pd.DataFrame):
                safe_globals['_tables'].append({
                    "title": title,
                    "columns": list(data.columns),
                    "rows": data.head(50).values.tolist()
                })
            elif isinstance(data, list):
                safe_globals['_tables'].append({
                    "title": title,
                    "rows": data[:50]
                })

        safe_globals['show_chart'] = show_chart
        safe_globals['show_table'] = show_table
        safe_globals['plt'] = plt

    except ImportError as e:
        pass

    # Output capture
    output = io.StringIO()

    try:
        # Execute code with captured output
        with contextlib.redirect_stdout(output):
            exec(code, safe_globals)

        output_text = output.getvalue()

        # Get charts from execution
        charts = safe_globals.get('_charts', [])
        tables = safe_globals.get('_tables', [])

        # Get data preview if df exists
        data_preview = None
        if df is not None and len(df) > 0:
            try:
                data_preview = f"DataFrame shape: {df.shape}\nLast 5 rows:\n{df.tail(5).to_string()}"
            except:
                pass

        # Auto-generate chart from df if no explicit charts
        if not charts and df is not None and len(df) > 0:
            try:
                if 'close' in df.columns:
                    charts.append({
                        "title": "Close Price",
                        "data": df['close'].tail(50).tolist(),
                        "color": "#22c55e",
                        "type": "line"
                    })
            except:
                pass

        # Universal JSON Sanitization
        def _sanitize(obj):
            import math
            from datetime import date, time, datetime
            if isinstance(obj, (datetime, pd.Timestamp)): return obj.isoformat()
            if isinstance(obj, (date, time)): return str(obj)
            if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)): return None
            if isinstance(obj, dict): return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)): return [_sanitize(i) for i in obj]
            return obj

        return {
            "success": True,
            "output": output_text if output_text else "Code executed successfully",
            "data_preview": data_preview,
            "charts": _sanitize(charts) if charts else None,
            "tables": _sanitize(tables) if tables else None,
            "modified_data": _sanitize(df.tail(100).to_dict('records')) if df is not None else None
        }

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        return {
            "success": False,
            "error": error_msg,
            "output": output.getvalue() if output.getvalue() else ""
        }



class CalculateIndicatorRequest(BaseModel):
    indicator: str
    period: int
    market_data: List[Dict[str, Any]]


@router.post("/calculate-indicator")
async def calculate_indicator(request: CalculateIndicatorRequest):
    """
    Calculate a technical indicator on market data.
    
    Supported indicators:
    - ATR (Average True Range)
    - SMA (Simple Moving Average)
    - EMA (Exponential Moving Average)
    - RSI (Relative Strength Index)
    """
    try:
        import pandas as pd
        
        # Create DataFrame
        df = pd.DataFrame(request.market_data)
        
        if request.indicator.upper() == 'ATR':
            # Calculate ATR
            df['tr'] = df.apply(
                lambda row: max(
                    row['high'] - row['low'],
                    abs(row['high'] - df.shift(1).close[row.name]) if row.name > 0 else row['high'] - row['low'],
                    abs(row['low'] - df.shift(1).close[row.name]) if row.name > 0 else row['high'] - row['low']
                ), axis=1
            )
            df['atr'] = df['tr'].rolling(window=request.period).mean()
            current_atr = round(df['atr'].iloc[-1], 2) if not pd.isna(df['atr'].iloc[-1]) else None
            
            return {
                "success": True,
                "indicator": "ATR",
                "period": request.period,
                "current_value": current_atr,
                "values": df['atr'].dropna().tolist()[-20:]
            }
            
        elif request.indicator.upper() == 'SMA':
            df['sma'] = df['close'].rolling(window=request.period).mean()
            current_sma = round(df['sma'].iloc[-1], 2) if not pd.isna(df['sma'].iloc[-1]) else None
            
            return {
                "success": True,
                "indicator": "SMA",
                "period": request.period,
                "current_value": current_sma,
                "values": df['sma'].dropna().tolist()[-20:]
            }
            
        elif request.indicator.upper() == 'EMA':
            df['ema'] = df['close'].ewm(span=request.period).mean()
            current_ema = round(df['ema'].iloc[-1], 2) if not pd.isna(df['ema'].iloc[-1]) else None
            
            return {
                "success": True,
                "indicator": "EMA",
                "period": request.period,
                "current_value": current_ema,
                "values": df['ema'].dropna().tolist()[-20:]
            }
            
        elif request.indicator.upper() == 'RSI':
            # Calculate RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=request.period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=request.period).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            current_rsi = round(df['rsi'].iloc[-1], 2) if not pd.isna(df['rsi'].iloc[-1]) else None
            
            return {
                "success": True,
                "indicator": "RSI",
                "period": request.period,
                "current_value": current_rsi,
                "values": df['rsi'].dropna().tolist()[-20:]
            }
        
        else:
            return {
                "success": False,
                "error": f"Unsupported indicator: {request.indicator}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }