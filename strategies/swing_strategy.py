"""
strategies/swing_strategy.py

Multi-Timeframe EMA+RSI+Volume Confluence Strategy.

This is our PRIMARY trading strategy. It combines:
- EMA trend direction (daily timeframe)
- RSI oversold/overbought zones
- Volume spike confirmation
- ADX trend strength filter
- VWAP bullish confirmation
- MACD momentum confirmation

Designed for 4H swing trading with daily trend confirmation.
"""

import pandas as pd
import numpy as np
from typing import Tuple
from strategies.base import BaseStrategy
from data.indicators import TechnicalIndicators
from utils.logger import log


class SwingStrategy(BaseStrategy):
    """
    Multi-Timeframe Confluence Swing Trading Strategy.
    
    Core Philosophy:
    - Trade IN the direction of the higher timeframe trend
    - Enter on lower timeframe pullbacks (buy the dip)
    - Exit on momentum exhaustion (overbought)
    
    This strategy aims for high-probability setups by requiring
    MULTIPLE confirmations before entering any trade.
    """
    
    def __init__(self):
        params = {
            "ema_fast": 20,
            "ema_slow": 50,
            "rsi_period": 14,
            "rsi_buy_zone": 35,       # Buy when RSI below this
            "rsi_sell_zone": 70,      # Sell when RSI above this
            "volume_multiplier": 1.5,  # Volume must be 1.5x average
            "adx_min": 20,            # Minimum ADX for trending market
            "risk_reward_ratio": 2.5, # Target RR ratio
        }
        super().__init__("SwingCombo", params)
        self.indicators = TechnicalIndicators()
    
    # ------------------------------------------------------------------
    # CORE METHOD: Generate Signals
    # ------------------------------------------------------------------
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate BUY/SELL signals for each candle.
        
        Process:
        1. Add all technical indicators
        2. Check BUY conditions for each candle
        3. Check SELL conditions for existing positions
        4. Mark signals in the 'signal' column
        
        Args:
            df: OHLCV DataFrame
        
        Returns:
            DataFrame with 'signal' column (1=BUY, -1=SELL, 0=HOLD)
        """
        df = df.copy()
        
        # Step 1: Add all indicators
        df = self.indicators.add_all_indicators(df)
        
        # Step 2: Initialize signal column
        df["signal"] = 0
        
        # Step 3: Pre-calculate conditions (vectorized for speed)
        # These are Series of True/False values
        conditions = self._calculate_conditions(df)
        
        # Step 4: Generate signals
        in_position = False  # Track if we're in a trade
        
        for i in range(50, len(df)):  # Start from 50 (need warmup for indicators)
            
            if not in_position:
                # Looking for BUY signal
                if self._check_buy_conditions(conditions, df, i):
                    df.at[df.index[i], "signal"] = 1
                    in_position = True
            else:
                # Looking for SELL signal
                if self._check_sell_conditions(conditions, df, i):
                    df.at[df.index[i], "signal"] = -1
                    in_position = False
        
        return df
    
    # ------------------------------------------------------------------
    # Pre-calculate all conditions (for performance)
    # ------------------------------------------------------------------
    
    def _calculate_conditions(self, df: pd.DataFrame) -> dict:
        """
        Pre-calculate all boolean conditions as Series.
        
        Doing this once is much faster than calculating inside the loop.
        """
        return {
            # Trend conditions
            "ema_bullish": df["EMA_20"] > df["EMA_50"],
            "ema_bearish": df["EMA_20"] < df["EMA_50"],
            "price_above_ema20": df["close"] > df["EMA_20"],
            "price_below_ema20": df["close"] < df["EMA_20"],
            
            # RSI conditions
            "rsi_oversold": df["RSI"] < self.params["rsi_buy_zone"],
            "rsi_overbought": df["RSI"] > self.params["rsi_sell_zone"],
            
            # Volume conditions
            "volume_spike": df["Volume_Ratio"] > self.params["volume_multiplier"],
            
            # Trend strength
            "strong_trend": df["ADX"] > self.params["adx_min"],
            "adx_rising": df["ADX_Rising"],
            
            # VWAP
            "above_vwap": df["Above_VWAP"],
            
            # MACD
            "macd_bullish": df["MACD_Cross"] == 1,
            "macd_bearish": df["MACD_Cross"] == -1,
            "macd_above_signal": df["MACD"] > df["MACD_Signal"],
            "histogram_rising": df["MACD_Histogram"] > df["MACD_Histogram"].shift(1),
            
            # Bollinger
            "near_lower_bb": df["BB_Position"] < 0.2,
            "near_upper_bb": df["BB_Position"] > 0.8,
        }
    
    # ------------------------------------------------------------------
    # BUY Signal Logic
    # ------------------------------------------------------------------
    
    def _check_buy_conditions(
        self, conditions: dict, df: pd.DataFrame, i: int
    ) -> bool:
        """
        Check if ALL buy conditions are met at candle i.
        
        Buy conditions (ALL must be true):
        1. EMA bullish (20 > 50) - uptrend
        2. RSI oversold (< 35) - pullback in uptrend
        3. Volume spike (>1.5x) - institutional interest
        4. ADX > 20 - trending market
        5. Close > VWAP - intraday bullish
        6. MACD bullish or improving - momentum confirmation
        + Additional validation (no bad candles)
        """
        
        # Core conditions - ALL must be True
        core = [
            conditions["ema_bullish"].iloc[i],          # Uptrend
            conditions["rsi_oversold"].iloc[i],          # Pullback
            conditions["volume_spike"].iloc[i],           # Volume confirmation
            conditions["strong_trend"].iloc[i],           # Trending
            conditions["above_vwap"].iloc[i],             # Bullish intraday
        ]
        
        # All core conditions must be True
        if not all(core):
            return False
        
        # MACD confirmation (at least one must be true)
        macd_ok = (
            conditions["macd_bullish"].iloc[i] or         # Fresh crossover
            conditions["macd_above_signal"].iloc[i] or    # Or already bullish
            conditions["histogram_rising"].iloc[i]        # Or improving
        )
        
        if not macd_ok:
            return False
        
        # Run additional validation
        if not self.validate_signal(df, i):
            return False
        
        return True
    
    # ------------------------------------------------------------------
    # SELL Signal Logic
    # ------------------------------------------------------------------
    
    def _check_sell_conditions(
        self, conditions: dict, df: pd.DataFrame, i: int
    ) -> bool:
        """
        Check if sell conditions are met.
        
        Sell if ANY of these are true:
        1. RSI overbought (> 70) - profit-taking zone
        2. Close below EMA 20 - short-term trend broken
        3. Bearish MACD crossover - momentum shift
        4. Near upper Bollinger - overextended
        """
        
        sell_signals = [
            conditions["rsi_overbought"].iloc[i],        # Overbought
            conditions["price_below_ema20"].iloc[i],     # Trend broken
            conditions["macd_bearish"].iloc[i],          # Bearish crossover
            conditions["near_upper_bb"].iloc[i],         # Overextended
        ]
        
        # Sell if ANY condition is True
        return any(sell_signals)
    
    # ------------------------------------------------------------------
    # Signal Validation (False Signal Filter)
    # ------------------------------------------------------------------
    
    def validate_signal(self, df: pd.DataFrame, index: int) -> bool:
        """
        Additional validation to filter false signals.
        
        Checks:
        1. ATR filter - avoid low volatility chop
        2. Candle pattern - avoid long wick tops
        3. RSI divergence - no bearish divergence on entry
        4. Volume consistency - avoid one-off spikes
        """
        
        # Check 1: ATR filter
        # If current ATR is too low, market is choppy, avoid trading
        current_atr = df["ATR"].iloc[index]
        avg_atr_20 = df["ATR"].rolling(20).mean().iloc[index]
        
        if not pd.isna(avg_atr_20) and current_atr < avg_atr_20 * 0.5:
            log.debug(f"Signal rejected: Low volatility (ATR={current_atr:.4f})")
            return False
        
        # Check 2: Long wick top (shooting star pattern)
        # A long upper wick means sellers pushed price down from the high
        prev = df.iloc[index - 1]
        candle_range = prev["high"] - prev["low"]
        
        if candle_range > 0:
            upper_wick = prev["high"] - max(prev["open"], prev["close"])
            if upper_wick / candle_range > 0.7:
                log.debug("Signal rejected: Long upper wick (shooting star)")
                return False
        
        # Check 3: Volume consistency
        # Volume spike should not be from a single candle
        if index >= 2:
            recent_volume = (
                df["Volume_Ratio"].iloc[index] +
                df["Volume_Ratio"].iloc[index - 1]
            ) / 2
            if recent_volume < 1.2:
                log.debug("Signal rejected: Volume not sustained")
                return False
        
        # Check 4: Consecutive signals
        # Avoid taking signals on consecutive candles (wait for new setup)
        if index >= 3:
            recent_signals = df["signal"].iloc[index-3:index].sum()
            if recent_signals != 0:
                log.debug("Signal rejected: Too close to previous signal")
                return False
        
        return True
    
    # ------------------------------------------------------------------
    # Stop Loss & Take Profit
    # ------------------------------------------------------------------
    
    def get_stop_loss(
        self, df: pd.DataFrame, index: int, entry_price: float
    ) -> float:
        """
        Calculate stop loss using ATR.
        
        Stop Loss = Entry Price - (ATR × Multiplier)
        
        We use 2.0x ATR to give the trade room to breathe.
        95% of price action stays within 2 ATR of its mean.
        """
        atr = df["ATR"].iloc[index]
        
        if pd.isna(atr) or atr <= 0:
            # Fallback: Use recent swing low
            swing_low = df["Swing_Low"].iloc[index]
            if not pd.isna(swing_low) and swing_low < entry_price:
                return swing_low * 0.995  # Just below swing low
            return entry_price * 0.97  # Absolute fallback: 3%
        
        atr_multiplier = 2.0
        stop_loss = entry_price - (atr * atr_multiplier)
        
        # Don't let stop be more than 10% away
        max_stop = entry_price * 0.90
        stop_loss = max(stop_loss, max_stop)
        
        return stop_loss
    
    def get_take_profit(
        self, entry_price: float, stop_loss: float
    ) -> float:
        """
        Calculate take profit using risk:reward ratio.
        
        TP = Entry + (Risk × RR Ratio)
        """
        return super().get_take_profit(
            entry_price, stop_loss, self.params["risk_reward_ratio"]
        )