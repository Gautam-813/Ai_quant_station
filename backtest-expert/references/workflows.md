# Backtest Generation Workflow

1. **Context Loading**:
   - Load raw M1 OHLC data from `sandbox_worker.py` (simulated).
   - Ensure the LLM understands columns: `['time', 'open', 'high', 'low', 'close', 'volume']`.

2. **Code Generation**:
   - The LLM MUST generate code that:
     - Defines an `execute_strategy(df)` function.
     - Resamples internally.
     - Computes indicators.
     - Handles errors.

3. **Validation (Mental/Agentic Check)**:
   - Does it use `for` loops for resampling? (If yes, FAIL).
   - Does it use `try/except` for the entire block? (If no, FAIL).
   - Does it output structured JSON on error? (If no, FAIL).

4. **Execution**:
   - Run in isolated sandbox.
