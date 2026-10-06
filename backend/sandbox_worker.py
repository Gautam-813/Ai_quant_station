#!/usr/bin/env python3
"""
Sandbox Worker — runs AI-generated Python code in an isolated subprocess.

Reads JSON from stdin, writes JSON to stdout.

Usage (internal, called by execute.py):
    python sandbox_worker.py < input.json > output.json

Security: runs with restricted builtins (no open/exec/eval/import of
dangerous modules). Each invocation is a fresh process; no state leaks.
"""

import sys
import json
import os

# Add backend/ to sys.path so we can import from app.*
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    try:
        request = json.loads(sys.stdin.read())
    except Exception as e:
        _respond({"success": False, "error": f"Invalid input JSON: {e}"})
        return

    code = request.get("code", "")
    market_data = request.get("market_data")
    symbol = request.get("symbol")
    session_state = request.get("session_state")

    # Import and run the core sandbox synchronously
    from app.api.execute import _execute_sandbox_sync

    result = _execute_sandbox_sync(
        code=code,
        market_data=market_data,
        symbol=symbol,
        session_state=session_state,
    )
    _respond(result)


def serve():
    """Persistent mode (--serve): one JSON request per stdin line, one JSON
    response per stdout line. Libraries stay imported across requests so
    repeated sandbox executions skip the ~1-2s interpreter/import startup.
    State still cannot leak between requests: user variables travel in the
    request's session_state, never in worker globals."""
    from app.api.execute import _execute_sandbox_sync

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except Exception as e:
            _respond_line({"success": False, "error": f"Invalid input JSON: {e}"})
            continue
        if request.get("command") == "exit":
            break
        result = _execute_sandbox_sync(
            code=request.get("code", ""),
            market_data=request.get("market_data"),
            symbol=request.get("symbol"),
            session_state=request.get("session_state"),
        )
        _respond_line(result)


def _respond(data: dict):
    sys.stdout.write(json.dumps(data))
    sys.stdout.flush()


def _respond_line(data: dict):
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        main()
