"""
Bar-by-bar Backtest Engine
Iterates through each bar calling the Strategy.on_bar() method.
Supports SL/TP, partial closes, breakeven SL, session tracking,
and time-based filters — anything the signal-based engine cannot do.
"""
import logging
import numpy as np
import pandas as pd
from typing import Optional
from collections import OrderedDict

logger = logging.getLogger(__name__)


class Strategy:
    """
    Base class for user-defined trading strategies.

    Subclass this and override on_bar().
    Use self to maintain state across bars (trade counters, timers, etc.).
    """

    def __init__(self):
        self.position = 0          # 0 = flat, 1 = long, -1 = short
        self.entry_price = 0.0
        self.entry_bar = 0
        self.position_fraction = 0.0   # 0.0 – 1.0
        self.sl_price = None
        self.tp_price = None
        self.trades_today = 0
        self.current_day = None

    def on_bar(self, df: pd.DataFrame, i: int) -> Optional[dict]:
        """
        Called for every bar.

        Return None to do nothing, or a dict with one of these shapes:

            {'action': 'BUY',  'sl': 1950.0, 'tp': 2100.0}
            {'action': 'SELL', 'sl': 2050.0, 'tp': 1900.0}
            {'action': 'CLOSE'}
            {'action': 'CLOSE_PARTIAL', 'fraction': 0.5}
            {'action': 'MODIFY_SL', 'sl': 1980.0}
            {'action': 'MODIFY_TP', 'tp': 2150.0}

        sl/tp are optional on entry.  Omit either to skip that level.
        SL/TP are checked at market open of each subsequent bar using
        high/low — if breached the position is closed at that level.
        """
        return None

    def reset(self):
        self.position = 0
        self.entry_price = 0.0
        self.entry_bar = 0
        self.position_fraction = 0.0
        self.sl_price = None
        self.tp_price = None
        self.trades_today = 0
        self.current_day = None


class BarByBacktestEngine:
    """
    Bar-by-bar engine with full position management.

    Output dict keys match BacktestEngine for frontend compatibility:
        equity_curve: list[dict]  …  {time: str, balance: float}
        metrics:      dict
        trade_log:    list[dict]
    """

    def __init__(self, initial_capital: float = 10000.0,
                 lot_size: float = 0.01,
                 contract_multiplier: float = 100.0,
                 spread_pips: float = 0.0,
                 commission_per_lot: float = 0.0):
        self.initial_capital = initial_capital
        self.lot_size = lot_size
        self.contract_multiplier = contract_multiplier
        self.spread_pips = spread_pips
        self.commission = commission_per_lot

    def run(self, df: pd.DataFrame, strategy_class) -> Optional[dict]:
        """
        Run the backtest.

        Parameters
        ----------
        df : pd.DataFrame
            Must contain columns: open, high, low, close, volume.
            May contain any indicator columns.
        strategy_class : Strategy subclass (not instance)
            The engine creates an instance internally.

        Returns
        -------
        dict or None
            Same shape as BacktestEngine.run() output.
        """
        df = df.copy()
        n = len(df)

        if n < 2:
            logger.error("Need at least 2 bars.")
            return None

        # ── Ensure DatetimeIndex so df.index[i] works for time logic ────────
        if not isinstance(df.index, pd.DatetimeIndex):
            if "datetime" in df.columns:
                df = df.set_index(pd.to_datetime(df.pop("datetime")))
            elif "timestamp" in df.columns:
                df = df.set_index(pd.to_datetime(df.pop("timestamp"), unit="s"))
        timestamps = df.index

        # ── Strategy instance ────────────────────────────────────────────────
        strat = strategy_class()
        strat.reset()

        # ── Execution state ──────────────────────────────────────────────────
        trades: list[dict] = []       # completed trades
        closed_pnl: float = 0.0
        equity_curve: list[dict] = []

        position = 0          # 1 / -1 / 0
        entry_price = 0.0
        entry_bar = 0
        entry_fraction = 0.0  # 0.0 – 1.0 of full lot
        sl_price: Optional[float] = None
        tp_price: Optional[float] = None
        has_position = False

        spread_cost = (self.spread_pips / 100) * self.lot_size * self.contract_multiplier

        # ── Main bar loop ────────────────────────────────────────────────────
        for i in range(n):
            row = df.iloc[i]
            close = float(row["close"])
            high = float(row["high"])
            low = float(row["low"])
            ts = timestamps[i]
            time_str = str(ts)

            # Day-roll for daily counters
            if hasattr(ts, "date"):
                day = ts.date()
                if day != strat.current_day:
                    strat.current_day = day
                    strat.trades_today = 0

            # ── SL / TP check (before strategy call) ──────────────────────────
            sl_hit = False
            tp_hit = False
            exit_price = close

            if has_position and sl_price is not None:
                if position == 1 and low <= sl_price:
                    sl_hit = True
                    exit_price = sl_price
                elif position == -1 and high >= sl_price:
                    sl_hit = True
                    exit_price = sl_price

            if has_position and tp_price is not None and not sl_hit:
                if position == 1 and high >= tp_price:
                    tp_hit = True
                    exit_price = tp_price
                elif position == -1 and low <= tp_price:
                    tp_hit = True
                    exit_price = tp_price

            if sl_hit or tp_hit:
                pnl = (
                    entry_fraction
                    * self.lot_size
                    * self.contract_multiplier
                    * (exit_price - entry_price)
                    * position
                )
                trades.append(self._make_trade(
                    df, entry_bar, i, entry_price, exit_price,
                    "BUY" if position == 1 else "SELL", pnl, timestamps,
                ))
                closed_pnl += pnl
                self._clear_position(strat)

                position = 0
                entry_price = 0.0
                entry_bar = 0
                entry_fraction = 0.0
                sl_price = None
                tp_price = None
                has_position = False

            # ── Strategy call ────────────────────────────────────────────────
            if not sl_hit and not tp_hit:
                action = strat.on_bar(df, i)
                if action and isinstance(action, dict):
                    act = action.get("action")

                    if act in ("BUY", "SELL") and not has_position:
                        new_pos = 1 if act == "BUY" else -1
                        position = new_pos
                        has_position = True
                        entry_price = close
                        entry_bar = i
                        entry_fraction = 1.0
                        sl_price = action.get("sl")
                        tp_price = action.get("tp")

                        strat.position = new_pos
                        strat.entry_price = close
                        strat.entry_bar = i
                        strat.position_fraction = 1.0
                        strat.sl_price = sl_price
                        strat.tp_price = tp_price

                        # Spread cost on entry
                        closed_pnl -= spread_cost

                    elif act == "CLOSE" and has_position:
                        pnl = (
                            entry_fraction
                            * self.lot_size
                            * self.contract_multiplier
                            * (close - entry_price)
                            * position
                        )
                        trades.append(self._make_trade(
                            df, entry_bar, i, entry_price, close,
                            "BUY" if position == 1 else "SELL", pnl, timestamps,
                        ))
                        closed_pnl += pnl
                        self._clear_position(strat)
                        position = 0
                        entry_price = 0.0
                        entry_bar = 0
                        entry_fraction = 0.0
                        sl_price = None
                        tp_price = None
                        has_position = False

                    elif act == "CLOSE_PARTIAL" and has_position:
                        fraction = min(
                            float(action.get("fraction", 0.5)), entry_fraction
                        )
                        pnl = (
                            fraction
                            * self.lot_size
                            * self.contract_multiplier
                            * (close - entry_price)
                            * position
                        )
                        trades.append(self._make_trade(
                            df, entry_bar, i, entry_price, close,
                            "BUY" if position == 1 else "SELL", pnl, timestamps,
                        ))
                        closed_pnl += pnl
                        entry_fraction -= fraction
                        strat.position_fraction = entry_fraction
                        if entry_fraction <= 0:
                            self._clear_position(strat)
                            position = 0
                            entry_price = 0.0
                            entry_bar = 0
                            sl_price = None
                            tp_price = None
                            has_position = False

                    elif act == "MODIFY_SL" and has_position:
                        sl_price = float(action["sl"])
                        strat.sl_price = sl_price

                    elif act == "MODIFY_TP" and has_position:
                        tp_price = float(action["tp"])
                        strat.tp_price = tp_price

            # ── Equity curve point ──────────────────────────────────────────
            unrealized = 0.0
            if has_position:
                unrealized = (
                    entry_fraction
                    * self.lot_size
                    * self.contract_multiplier
                    * (close - entry_price)
                    * position
                )
            equity_curve.append({
                "time": time_str,
                "balance": round(self.initial_capital + closed_pnl + unrealized, 2),
            })

        # ── Close remaining at end of data ────────────────────────────────────
        if has_position:
            last_close = float(df.iloc[-1]["close"])
            pnl = (
                entry_fraction
                * self.lot_size
                * self.contract_multiplier
                * (last_close - entry_price)
                * position
            )
            trades.append(self._make_trade(
                df, entry_bar, n - 1, entry_price, last_close,
                "BUY" if position == 1 else "SELL", pnl, timestamps,
                exit_time_label="END OF DATA",
            ))
            closed_pnl += pnl

        # ── Compute metrics ──────────────────────────────────────────────────
        total_pnl = closed_pnl
        final_equity = self.initial_capital + total_pnl
        total_return_pct = (final_equity / self.initial_capital - 1) * 100

        winning = [t for t in trades if t["pnl"] > 0]
        win_rate_pct = (len(winning) / len(trades) * 100) if trades else 0.0

        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] <= 0))
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0.0)
        )

        # Max Drawdown
        eq_series = pd.Series([e["balance"] for e in equity_curve])
        roll_max = eq_series.cummax()
        max_dd_pct = float(((eq_series / roll_max - 1) * 100).min())

        # Sharpe ratio (annualized from bar returns)
        eq_returns = eq_series.pct_change().dropna()
        sharpe = 0.0
        if len(eq_returns) > 1 and eq_returns.std() > 0:
            periods_per_year = 252 * 24 * 60  # 1-minute default
            sharpe = float(
                (eq_returns.mean() / eq_returns.std()) * np.sqrt(periods_per_year)
            )

        # Sample equity curve
        step = max(1, len(equity_curve) // 500)
        sampled = equity_curve[::step]

        return OrderedDict([
            ("equity_curve", sampled),
            ("metrics", OrderedDict([
                ("total_return_pct", round(total_return_pct, 2)),
                ("total_pnl", round(total_pnl, 2)),
                ("sharpe_ratio", round(sharpe, 3)),
                ("max_drawdown_pct", round(max_dd_pct, 2)),
                ("win_rate_pct", round(win_rate_pct, 2)),
                ("profit_factor", round(profit_factor, 3)),
                ("num_trades", len(trades)),
                ("final_equity", round(final_equity, 2)),
                ("lot_size", self.lot_size),
            ])),
            ("trade_log", trades),
        ])

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_trade(df, entry_bar, exit_bar, entry_price, exit_price,
                    direction, pnl, timestamps, exit_time_label=None):
        entry_ts = timestamps[entry_bar]
        exit_ts = timestamps[exit_bar] if exit_time_label is None else exit_time_label
        return OrderedDict([
            ("entry_time", str(entry_ts)),
            ("exit_time", str(exit_ts)),
            ("direction", direction),
            ("entry_price", round(float(entry_price), 2)),
            ("exit_price", round(float(exit_price), 2)),
            ("pnl", round(float(pnl), 2)),
        ])

    @staticmethod
    def _clear_position(strat):
        strat.position = 0
        strat.position_fraction = 0.0
        strat.sl_price = None
        strat.tp_price = None
