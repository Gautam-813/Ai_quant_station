"""
Vectorized Backtest Engine
Simulates trades on historical data and returns
performance metrics + equity curve data.
"""
import logging
import numpy as np
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Professional vectorized backtesting engine.
    Accepts a DataFrame with signal columns and calculates
    full performance statistics.
    """

    def __init__(self, initial_capital: float = 10000.0, leverage: float = 100.0,
                 spread_pips: float = 0.0, commission_per_lot: float = 0.0):
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.spread_pips = spread_pips
        self.commission = commission_per_lot

    def run(self, df: pd.DataFrame) -> Optional[dict]:
        """
        Run the backtest.
        Expects df to have a 'signal' column:
            1  = BUY
           -1  = SELL
            0  = NO POSITION

        Returns a dict with:
            - equity_curve: list of {time, balance} for charting
            - metrics: dict of performance stats
            - trade_log: list of individual trades
        """
        if "signal" not in df.columns:
            logger.error("DataFrame must have a 'signal' column.")
            return None

        df = df.copy()
        df["signal"] = df["signal"].fillna(0)

        # --- Vectorized PnL Calculation ---
        # Price return per bar
        df["return"] = df["close"].pct_change().fillna(0)

        # Strategy return = signal * market return * leverage
        df["strategy_return"] = df["signal"].shift(1).fillna(0) * df["return"] * self.leverage

        # Apply spread cost on each trade entry (signal change)
        df["signal_change"] = df["signal"].diff().abs()
        df["spread_cost"] = df["signal_change"] * (self.spread_pips / 10000)
        df["strategy_return"] -= df["spread_cost"]

        # Equity curve
        df["equity"] = self.initial_capital * (1 + df["strategy_return"]).cumprod()

        # --- Performance Metrics ---
        total_return = (df["equity"].iloc[-1] / self.initial_capital - 1) * 100
        max_drawdown = self._max_drawdown(df["equity"])
        sharpe = self._sharpe_ratio(df["strategy_return"])
        win_rate, profit_factor, num_trades = self._trade_stats(df)

        # --- Equity Curve for Chart ---
        # Sample to max 500 points for frontend performance
        step = max(1, len(df) // 500)
        sampled = df.iloc[::step][["datetime", "equity"]].copy()
        sampled["datetime"] = sampled["datetime"].astype(str)

        equity_curve = sampled.rename(columns={"datetime": "time", "equity": "balance"}).to_dict("records")

        return {
            "equity_curve": equity_curve,
            "metrics": {
                "total_return_pct": round(total_return, 2),
                "sharpe_ratio": round(sharpe, 3),
                "max_drawdown_pct": round(max_drawdown, 2),
                "win_rate_pct": round(win_rate, 2),
                "profit_factor": round(profit_factor, 3),
                "num_trades": num_trades,
                "final_equity": round(df["equity"].iloc[-1], 2),
            },
        }

    def _max_drawdown(self, equity: pd.Series) -> float:
        """Calculate maximum drawdown as a percentage."""
        roll_max = equity.cummax()
        drawdown = (equity - roll_max) / roll_max
        return float(drawdown.min() * 100)

    def _sharpe_ratio(self, returns: pd.Series, periods_per_year: int = 252 * 24 * 60) -> float:
        """Annualized Sharpe Ratio (for 1-minute data)."""
        if returns.std() == 0:
            return 0.0
        return float((returns.mean() / returns.std()) * np.sqrt(periods_per_year))

    def _trade_stats(self, df: pd.DataFrame) -> tuple:
        """Calculate win rate, profit factor, and number of trades."""
        # Identify trade entries and exits
        df["position"] = df["signal"].shift(1).fillna(0)
        df["trade_pnl"] = df["strategy_return"] * self.initial_capital

        # Segment into individual trades
        trade_returns = []
        in_trade = False
        trade_pnl = 0

        for _, row in df.iterrows():
            if row["signal"] != 0 and not in_trade:
                in_trade = True
                trade_pnl = 0
            elif row["signal"] == 0 and in_trade:
                trade_returns.append(trade_pnl)
                in_trade = False
            if in_trade:
                trade_pnl += row["trade_pnl"]

        if not trade_returns:
            return 0.0, 0.0, 0

        wins = [t for t in trade_returns if t > 0]
        losses = [t for t in trade_returns if t <= 0]
        win_rate = (len(wins) / len(trade_returns)) * 100
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss else float("inf")

        return win_rate, profit_factor, len(trade_returns)


class DeepAnalysisEngine:
    """
    Market behavior analysis engine.
    Returns statistical insights: volatility heatmaps, 
    day-of-week patterns, session analysis, etc.
    """

    def run(self, df: pd.DataFrame) -> dict:
        df = df.copy()
        df["hour"] = df["datetime"].dt.hour
        df["day_of_week"] = df["datetime"].dt.day_name()
        df["range"] = df["high"] - df["low"]  # Volatility proxy

        # Volatility by Hour (Heatmap data)
        hourly_vol = (
            df.groupby("hour")["range"]
            .mean()
            .round(5)
            .reset_index()
            .rename(columns={"hour": "hour_utc", "range": "avg_range"})
            .to_dict("records")
        )

        # Volatility by Day of Week
        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        dow_vol = (
            df.groupby("day_of_week")["range"]
            .mean()
            .round(5)
            .reindex(dow_order)
            .reset_index()
            .rename(columns={"day_of_week": "day", "range": "avg_range"})
            .to_dict("records")
        )

        # Daily Close Return Distribution
        df["daily_return"] = df["close"].pct_change() * 100

        # Summary stats
        stats = {
            "mean_return_pct": round(float(df["daily_return"].mean()), 4),
            "std_return_pct": round(float(df["daily_return"].std()), 4),
            "best_day": df.loc[df["daily_return"].idxmax(), "datetime"].strftime("%Y-%m-%d"),
            "worst_day": df.loc[df["daily_return"].idxmin(), "datetime"].strftime("%Y-%m-%d"),
            "total_bars": len(df),
        }

        return {
            "hourly_volatility": hourly_vol,
            "day_of_week_volatility": dow_vol,
            "stats": stats,
        }
