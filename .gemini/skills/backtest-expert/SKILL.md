---
name: backtest-expert
description: Expert system for robust, performant backtest code generation and execution. Use when generating, analyzing, or validating trading strategies to ensure multi-timeframe resampling, sandbox compatibility, and rigorous error handling.
---

# Backtest Expert Workflow

## When to use
Trigger this skill whenever you need to:
1. Generate Python backtest strategies.
2. Troubleshoot failed backtests.
3. Review or validate generated trading code.

## Core Mandates for Generated Code

Any code generated for backtesting MUST adhere to these strict constraints:

### 1. Performance & Sandbox Safety
- **Vectorization**: MUST use `pandas` vectorization. Absolutely NO explicit `for` loops for resampling or indicator calculation.
- **Resampling**: Explicitly resample raw M1 data to target timeframes (e.g., H1, M15).
- **Efficiency**: Must complete execution within 5 seconds and stay under 512MB RAM usage.
- **Edge Cases**: Must explicitly handle `NaN` values resulting from indicator calculations (e.g., `fillna` or `dropna`).

### 2. Error Handling & Reporting
- **Try-Except**: Wrap all logic in a `try...except` block.
- **Reporting**: If metrics fail to compute, the script MUST print a structured JSON error object to stdout: `{"status": "failed", "error": "description"}`. Do not let the script fail silently.

### 3. Schema Enforcement
- Generated code must produce a dictionary or JSON output containing standard metrics.

## Implementation Guide
Follow the workflow defined in [workflows.md](references/workflows.md).
Check specific constraint patterns in [patterns.md](references/patterns.md).
