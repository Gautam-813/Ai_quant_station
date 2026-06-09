# Code Pattern Constraints

## Recommended Resampling Pattern

```python
import pandas as pd

# Assume df is M1 OHLC DataFrame with 'time' as index
# Efficient H1 resampling
h1_df = df.resample('1H').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum'
}).dropna()
```

## Recommended Indicator Pattern

```python
# Using vectorized pandas for RSI
delta = h1_df['close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
h1_df['rsi'] = 100 - (100 / (1 + rs))
```
