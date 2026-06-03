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
    Uses fixed lot-size PnL calculation (not leverage-based).
    For XAUUSD with 0.01 lot: $1 price move = $1 PnL (contract_multiplier=100).
    """

    def __init__(self, initial_capital: float = 10000.0, lot_size: float = 0.01,
                 contract_multiplier: float = 100.0, spread_pips: float = 0.0,
                 commission_per_lot: float = 0.0):
        self.initial_capital = initial_capital
        self.lot_size = lot_size
        self.contract_multiplier = contract_multiplier
        self.spread_pips = spread_pips
        self.commission = commission_per_lot

    def run(self, df: pd.DataFrame) -> Optional[dict]:
        """
        Run the backtest.
        Expects df to have a 'signal' column:
            1  = BUY
           -1  = SELL
            0  = NO POSITION

        PnL = signal * lot_size * contract_multiplier * price_move
        For XAUUSD 0.01 lot: $1 price move → $1 PnL.

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

        # --- Lot-based PnL Calculation ---
        # Absolute price move per bar
        df["price_move"] = df["close"].diff().fillna(0)

        # PnL per bar based on fixed lot size
        # signal.shift(1) so entry bar uses signal=0 → no PnL
        df["bar_pnl"] = df["signal"].shift(1).fillna(0) * self.lot_size * self.contract_multiplier * df["price_move"]

        # Spread cost (pips → price units; for XAUUSD 1 pip ≈ 0.01)
        # Charge spread only on entries (0→1, 0→-1, or 1→-1 / -1→1 reversals)
        # NOT on exits (1→0, -1→0)
        signal_prev = df["signal"].shift(1).fillna(0)
        df["is_entry"] = (df["signal"] != 0) & (signal_prev != df["signal"])
        df["entry_cost"] = df["is_entry"].astype(float) * (self.spread_pips / 100) * self.lot_size * self.contract_multiplier
        df["bar_pnl"] -= df["entry_cost"]

        # Commission per round-turn (charged on entry only)
        df["commission_cost"] = df["is_entry"].astype(float) * self.commission * self.lot_size
        df["bar_pnl"] -= df["commission_cost"]

        # Equity curve
        df["equity"] = self.initial_capital + df["bar_pnl"].cumsum()

        # Strategy return (percentage) for sharpe / drawdown calculations
        df["strategy_return"] = df["bar_pnl"] / self.initial_capital

        # --- Performance Metrics ---
        total_pnl = df["bar_pnl"].sum()
        total_return = (total_pnl / self.initial_capital) * 100
        max_drawdown = self._max_drawdown(df["equity"])
        sharpe = self._sharpe_ratio(df["strategy_return"])
        win_rate, profit_factor, num_trades, trade_log = self._trade_stats(df, df["bar_pnl"])

        # --- Equity Curve for Chart ---
        step = max(1, len(df) // 500)
        sampled = df.iloc[::step][["datetime", "equity"]].copy()
        sampled["datetime"] = sampled["datetime"].astype(str)
        equity_curve = sampled.rename(columns={"datetime": "time", "equity": "balance"}).to_dict("records")

        return {
            "equity_curve": equity_curve,
            "metrics": {
                "total_return_pct": round(total_return, 2),
                "total_pnl": round(total_pnl, 2),
                "sharpe_ratio": round(sharpe, 3),
                "max_drawdown_pct": round(max_drawdown, 2),
                "win_rate_pct": round(win_rate, 2),
                "profit_factor": round(profit_factor, 3),
                "num_trades": num_trades,
                "final_equity": round(df["equity"].iloc[-1], 2),
                "lot_size": self.lot_size,
            },
            "trade_log": trade_log,
        }

    def _max_drawdown(self, equity: pd.Series) -> float:
        """Calculate maximum drawdown as a percentage."""
        roll_max = equity.cummax()
        drawdown = (equity - roll_max) / roll_max
        return float(drawdown.min() * 100)

    def _sharpe_ratio(self, returns: pd.Series, periods_per_year: Optional[int] = None) -> float:
        if returns.std() == 0:
            return 0.0
        if periods_per_year is None:
            periods_per_year = 252 * 24 * 60
        return float((returns.mean() / returns.std()) * np.sqrt(periods_per_year))

    def _trade_stats(self, df: pd.DataFrame, bar_pnl: pd.Series) -> tuple:
        trade_returns = []
        trade_log = []
        in_trade = False
        current_position = 0
        trade_pnl = 0
        entry_time = None
        entry_price = None

        signals = df["signal"].values
        closes = df["close"].values
        datetimes = df["datetime"].values if "datetime" in df.columns else df.index.values
        bar_pnl_values = bar_pnl.values if isinstance(bar_pnl, pd.Series) else bar_pnl
        n = len(df)

        for i in range(n):
            signal = signals[i]
            if in_trade:
                trade_pnl += bar_pnl_values[i]
            if signal != 0 and signal != current_position and not in_trade:
                in_trade = True
                current_position = signal
                trade_pnl = 0
                entry_time = datetimes[i]
                entry_price = closes[i]
            elif in_trade and signal == 0:
                trade_returns.append(trade_pnl)
                trade_log.append({
                    "entry_time": str(entry_time) if entry_time is not None else "",
                    "exit_time": str(datetimes[i]),
                    "direction": "BUY" if current_position == 1 else "SELL",
                    "entry_price": round(float(entry_price), 2) if entry_price else 0,
                    "exit_price": round(float(closes[i]), 2),
                    "pnl": round(float(trade_pnl), 2),
                })
                in_trade = False
                current_position = 0
                entry_time = None
                entry_price = None
            elif in_trade and signal != 0 and signal != current_position:
                trade_returns.append(trade_pnl)
                trade_log.append({
                    "entry_time": str(entry_time) if entry_time is not None else "",
                    "exit_time": str(datetimes[i]),
                    "direction": "BUY" if current_position == 1 else "SELL",
                    "entry_price": round(float(entry_price), 2) if entry_price else 0,
                    "exit_price": round(float(closes[i]), 2),
                    "pnl": round(float(trade_pnl), 2),
                })
                current_position = signal
                trade_pnl = 0
                entry_time = datetimes[i]
                entry_price = closes[i]

        if in_trade:
            trade_returns.append(trade_pnl)
            trade_log.append({
                "entry_time": str(entry_time) if entry_time is not None else "",
                "exit_time": "END OF DATA",
                "direction": "BUY" if current_position == 1 else "SELL",
                "entry_price": round(float(entry_price), 2) if entry_price else 0,
                "exit_price": round(float(closes[-1]), 2),
                "pnl": round(float(trade_pnl), 2),
            })

        if not trade_returns:
            return 0.0, 0.0, 0, []

        wins = [t for t in trade_returns if t > 0]
        losses = [t for t in trade_returns if t <= 0]
        win_rate = (len(wins) / len(trade_returns)) * 100
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

        return win_rate, profit_factor, len(trade_returns), trade_log


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
        daily_return_clean = df["daily_return"].dropna()
        best_day = "N/A"
        worst_day = "N/A"
        if not daily_return_clean.empty:
            best_day = df.loc[daily_return_clean.idxmax(), "datetime"].strftime("%Y-%m-%d") if daily_return_clean.idxmax() in df.index else "N/A"
            worst_day = df.loc[daily_return_clean.idxmin(), "datetime"].strftime("%Y-%m-%d") if daily_return_clean.idxmin() in df.index else "N/A"
        stats = {
            "mean_return_pct": round(float(df["daily_return"].mean()), 4),
            "std_return_pct": round(float(df["daily_return"].std()), 4),
            "best_day": best_day,
            "worst_day": worst_day,
            "avg_atr_14": round(float(df["atr_14"].mean()), 5) if "atr_14" in df.columns else 0,
            "total_bars": len(df),
        }

        return {
            "hourly_volatility": hourly_vol,
            "day_of_week_volatility": dow_vol,
            "stats": stats,
        }
