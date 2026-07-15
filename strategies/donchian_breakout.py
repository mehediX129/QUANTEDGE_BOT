"""
strategies/donchian_breakout.py

Donchian Channel Ensemble Breakout Strategy — BTC-specific.

RESEARCH BASIS:
Zarattini, Pagani & Barbon (2025), "Catching Crypto Trends: A Tactical
Approach for Bitcoin and Altcoins", Swiss Finance Institute Research
Paper No. 25-80. (SSRN abstract_id=5209907, verified genuine)

WHY THIS EXISTS SEPARATELY FROM SwingStrategy:
Research (Brauneis & Mestel 2018; the SFI paper above) shows BTC is
more liquid and more statistically efficient than ETH/SOL/ADA — its
dips get absorbed by institutional order flow spread over time rather
than forming the sharp V-shaped reversals that RSI-pullback logic is
built to catch. BTC trend-continues at highs and mean-reverts sharply
only at lows (asymmetric). Breakout entry (buy strength) fits this
better than pullback entry (buy weakness).

This does NOT replace SwingStrategy for ETH/SOL/ADA — only use this
for BTC. Keep SwingStrategy running unmodified for the other three.

METHODOLOGY (from the paper):
1. Multiple Donchian channels at different lookback periods (ensemble,
   not a single parameter set — reduces overfitting to one lookback).
2. Entry: price closes above the upper channel of a MAJORITY of the
   lookback periods (vote-based, not "any one").
3. Exit: price closes below the LOWER channel of the SAME lookback
   that triggered entry (trend-following exit, not RSI-overbought).
4. Position sizing: inverse to volatility (ATR-normalized) — bigger
   size in calm trends, smaller size in choppy/volatile ones.

This is deliberately simpler than the full paper (which does portfolio
rotation across 20 coins) — adapted here for a single-asset (BTC/USDT)
spot swing bot.
"""

import pandas as pd
import numpy as np
from typing import Dict, List
from strategies.base import BaseStrategy
from utils.logger import log

# NOTE: after copying this file into strategies/donchian_breakout.py,
# update strategies/__init__.py like this:
#
#     from strategies.swing_strategy import SwingStrategy
#     from strategies.donchian_breakout import DonchianBreakoutStrategy
#
#     STRATEGIES = {
#         "swing_combo": SwingStrategy,
#         "donchian_breakout": DonchianBreakoutStrategy,
#     }
#
#     # Per-symbol strategy assignment — this is the key structural change.
#     # BTC gets breakout logic (research-backed), others keep the
#     # existing pullback confluence strategy (unmodified, still working
#     # per your earlier positive Sharpe on ETH/SOL/ADA).
#     SYMBOL_STRATEGY_MAP = {
#         "BTC/USDT": "donchian_breakout",
#         "ETH/USDT": "swing_combo",
#         "SOL/USDT": "swing_combo",
#         "ADA/USDT": "swing_combo",
#     }


class DonchianBreakoutStrategy(BaseStrategy):
    """
    Multi-Lookback Donchian Channel Ensemble Breakout Strategy.

    Use this ONLY for BTC/USDT. For ETH/SOL/ADA keep SwingStrategy.

    Core Philosophy (opposite of SwingStrategy):
    - Trade breakouts (new highs), not pullbacks (dips).
    - Multiple lookback periods vote together (ensemble), not one
      fixed parameter set — this is what reduces overfitting risk.
    - Position size shrinks in high volatility, grows in low
      volatility (inverse-volatility sizing), instead of a fixed
      risk percentage regardless of regime.
    """

    def __init__(self, lookback_periods: List[int] = None):
        params = {
            # Ensemble of lookback periods. Research uses multiple
            # periods spanning short/medium/long trend horizons.
            # These are a reasonable starting set for 4H candles —
            # NOT copied from the paper (paper used daily-ish data),
            # so these must be walk-forward validated on your own
            # 4H BTC data before trusting them.
            "lookback_periods": lookback_periods or [10, 20, 55],
            # Minimum fraction of lookbacks that must agree for entry
            "vote_threshold": 0.5,  # majority vote (>=50%)
            "atr_period": 14,
            # Target risk per trade in ATR units — used for
            # volatility-normalized position sizing
            "atr_risk_multiplier": 2.0,
        }
        super().__init__("DonchianBreakoutBTC", params)

    # ------------------------------------------------------------------
    # CORE METHOD: Generate Signals
    # ------------------------------------------------------------------

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate BUY/SELL signals using Donchian ensemble breakout logic.

        Args:
            df: OHLCV DataFrame (expects 'high', 'low', 'close', 'volume')

        Returns:
            DataFrame with 'signal' column (1=BUY, -1=SELL, 0=HOLD)
            plus the per-lookback channel columns for inspection/debugging.
        """
        df = df.copy()
        df = self._add_donchian_channels(df)
        df = self._add_atr(df)

        df["signal"] = 0
        max_lookback = max(self.params["lookback_periods"])
        in_position = False
        entry_lookback_used = None  # which lookback's lower band to watch for exit

        for i in range(max_lookback + 5, len(df)):
            if not in_position:
                triggered, which_lookback = self._check_breakout(df, i)
                if triggered and self.validate_signal(df, i):
                    df.at[df.index[i], "signal"] = 1
                    in_position = True
                    entry_lookback_used = which_lookback
            else:
                if self._check_exit(df, i, entry_lookback_used):
                    df.at[df.index[i], "signal"] = -1
                    in_position = False
                    entry_lookback_used = None

        return df

    # ------------------------------------------------------------------
    # Donchian Channels (one pair of high/low bands per lookback)
    # ------------------------------------------------------------------

    def _add_donchian_channels(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add upper/lower Donchian channel columns for each lookback period.

        Upper channel = highest high over the lookback window (EXCLUDING
        the current candle, to avoid lookahead bias — a breakout must
        clear the PRIOR range, not include itself in the range).
        Lower channel = lowest low over the lookback window, same rule.
        """
        for period in self.params["lookback_periods"]:
            # shift(1) excludes the current candle from its own channel —
            # critical to avoid lookahead bias. Without this, a candle
            # could never "break out" of a channel that includes itself.
            df[f"Donchian_Upper_{period}"] = (
                df["high"].shift(1).rolling(window=period).max()
            )
            df[f"Donchian_Lower_{period}"] = (
                df["low"].shift(1).rolling(window=period).min()
            )
        return df

    def _add_atr(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add ATR for volatility-normalized position sizing."""
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["ATR"] = true_range.rolling(window=self.params["atr_period"]).mean()
        return df

    # ------------------------------------------------------------------
    # Entry: Ensemble Vote
    # ------------------------------------------------------------------

    def _check_breakout(self, df: pd.DataFrame, i: int):
        """
        Check if price closes above the upper Donchian channel for a
        MAJORITY of lookback periods (ensemble vote, not a single one).

        Returns:
            (triggered: bool, which_lookback: int or None)
            which_lookback = the SHORTEST period that triggered, used
            later to decide which lower-band to watch for the exit.
        """
        close = df["close"].iloc[i]
        votes = []
        triggered_periods = []

        for period in self.params["lookback_periods"]:
            upper = df[f"Donchian_Upper_{period}"].iloc[i]
            if pd.isna(upper):
                votes.append(False)
                continue
            is_breakout = close > upper
            votes.append(is_breakout)
            if is_breakout:
                triggered_periods.append(period)

        vote_fraction = sum(votes) / len(votes)
        triggered = vote_fraction >= self.params["vote_threshold"]

        # Use the shortest triggered lookback's lower band for the exit —
        # this makes the exit more responsive than waiting for the
        # longest lookback's lower band, which would give back more profit.
        which_lookback = min(triggered_periods) if triggered_periods else None

        return triggered, which_lookback

    # ------------------------------------------------------------------
    # Exit: Trend-Following (NOT RSI-overbought — that's pullback logic)
    # ------------------------------------------------------------------

    def _check_exit(self, df: pd.DataFrame, i: int, entry_lookback: int) -> bool:
        """
        Exit when price closes below the LOWER Donchian channel of the
        lookback period that triggered entry. This lets winners run
        (trend-following exit) instead of exiting on RSI-overbought,
        which would cut trend-continuation trades short — exactly the
        mismatch the research identifies with pullback-style logic.
        """
        if entry_lookback is None:
            entry_lookback = self.params["lookback_periods"][0]

        close = df["close"].iloc[i]
        lower = df[f"Donchian_Lower_{entry_lookback}"].iloc[i]

        if pd.isna(lower):
            return False

        return close < lower

    # ------------------------------------------------------------------
    # Signal Validation
    # ------------------------------------------------------------------

    def validate_signal(self, df: pd.DataFrame, index: int) -> bool:
        """
        Minimal validation — avoid entries with no ATR data yet
        (warmup period) and avoid re-entering immediately after an exit
        on the very next candle (whipsaw protection).
        """
        atr = df["ATR"].iloc[index]
        if pd.isna(atr) or atr <= 0:
            return False

        # Whipsaw guard: don't re-enter within 2 candles of the last exit
        if index >= 2:
            recent_signals = df["signal"].iloc[index - 2:index].sum()
            if recent_signals != 0:
                log.debug("Donchian signal rejected: too close to previous signal")
                return False

        return True

    # ------------------------------------------------------------------
    # Volatility-Normalized Position Sizing
    # ------------------------------------------------------------------

    def get_position_size_multiplier(self, df: pd.DataFrame, index: int) -> float:
        """
        Returns a MULTIPLIER (not an absolute size) to scale whatever
        RiskManager.calculate_position_size() would normally return.

        Research finding: this is what took BTC buy-and-hold's 80%+ max
        drawdown down to ~19% in the ensemble backtest — inverse-vol
        sizing, not a fixed % risk regardless of current volatility.

        Logic: compare current ATR to its own 50-candle rolling average.
        If current ATR is HIGHER than average (choppier/more volatile
        right now) -> reduce size. If LOWER (calmer) -> allow full size.

        This multiplier should be applied by whatever code calls this
        strategy, on top of RiskManager's existing fixed-fractional
        sizing — it does not replace RiskManager, it scales its output.
        """
        atr = df["ATR"].iloc[index]
        atr_avg = df["ATR"].rolling(50).mean().iloc[index]

        if pd.isna(atr) or pd.isna(atr_avg) or atr_avg <= 0:
            return 1.0  # not enough data yet, don't scale

        ratio = atr_avg / atr  # inverse: higher current vol -> smaller ratio
        # Cap the multiplier so a very calm market doesn't oversize,
        # and a very volatile market doesn't zero out the position
        return max(0.3, min(ratio, 1.5))

    # ------------------------------------------------------------------
    # Stop Loss & Take Profit — ATR-based, trend-following style
    # ------------------------------------------------------------------

    def get_stop_loss(self, df: pd.DataFrame, index: int, entry_price: float) -> float:
        """ATR-based stop, wider than SwingStrategy's since this holds
        trends longer (research: hold period is trend-length-dependent,
        not a fixed few candles)."""
        atr = df["ATR"].iloc[index]
        if pd.isna(atr) or atr <= 0:
            return entry_price * 0.95
        return entry_price - (atr * self.params["atr_risk_multiplier"])

    def get_take_profit(self, entry_price: float, stop_loss: float) -> float:
        """
        No fixed take-profit — this strategy is designed to let trends
        run and exit via the trailing Donchian lower-band exit instead.
        Returning a very high placeholder so any code expecting a TP
        value doesn't break; the REAL exit is _check_exit() above.
        """
        risk = abs(entry_price - stop_loss)
        return entry_price + (risk * 10)  # effectively "let it run"
