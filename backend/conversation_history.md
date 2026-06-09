# Conversation History: Backtest Troubleshooting & Refinement

## Session Overview
- **Date:** Wednesday, 3 June 2026
- **Current Project:** `impulse_analyst_v2/backend`
- **Topic:** Fixing Backtest Silent Failure Bug / Refining AI Code Generation for Multi-TF Resampling

---

## Key Technical Findings

### 1. The Silent Failure Bug
- **Issue:** Backtest tasks were marked as "completed" by the `historical_lab` service even when the backtest engine failed to produce valid results (`null` metrics).
- **Resolution:**
  - Modified `_generate_initial_report` to explicitly return a failure message when metrics are missing.
  - Updated `run_backtest_task` to set the task status to `failed` and record an error message when no metrics are generated, ensuring the UI accurately reflects the failure.

### 2. Backtest Execution Issues
- **Issue:** Strategy prompts were resulting in "Analysis complete" with null metrics.
- **Root Cause Analysis (ID 8):** Inspected `generated_code` for failed backtest ID 8. The LLM failed to implement the strategy, outputting only comments regarding missing ADX data and stopping execution. The system did not treat this incomplete/empty code as a hard error.

### 3. Understanding the Execution Model
- **Code Execution:** Code generation occurs via an LLM (Groq/NVIDIA), but the actual execution happens on the **backend** (within a Python sandbox environment), *not* the browser.
- **Refinement Strategy:** Instead of relying on backend-precomputed indicators, the AI must be explicitly instructed to utilize the raw M1 OHLC DataFrame provided in the sandbox to resample and compute all required indicators (H1, M15, M5) independently.

---

## Strategy for Success
To ensure successful backtest execution, the following prompt adjustment is required:

> "You have access to a raw M1 OHLC DataFrame `df`. **Do not rely on pre-existing indicators.** You must explicitly resample `df` to H1, M15, and M5 timeframes within your Python code to calculate all necessary indicators (EMA, ADX, RSI) from scratch using `pandas`. Then, align all signals back to the M15 timeframe for entry logic."

---
