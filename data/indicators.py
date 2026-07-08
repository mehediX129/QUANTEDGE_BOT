"""
data/indicators.py

Technical Indicators Engine.
Calculates all technical indicators needed for our strategies.
Uses pandas-ta library for professional-grade calculations.

Indicators implemented:
- EMA (Exponential Moving Average)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- ATR (Average True Range)
- ADX (Average Directional Index)
- Bollinger Bands
- Volume Moving Average
- VWAP (Volume Weighted Average Price)
"""

import pandas as pd
import numpy as np
import pandas_ta as ta
from typing import Optional
from utils.logger import log
import warnings


class TechnicalIndicators:
    """
    Technical indicator calculator.
    
    All methods are static because they don't need instance state.
    Input: DataFrame with OHLCV data
    Output: DataFrame with added indicator columns
    
    Usage:
        df = TechnicalIndicators.add_all_indicators(df)
        divergence = TechnicalIndicators.detect_divergence(df, "RSI")
    """
    
        # ------------------------------------------------------------------
    # MASTER METHOD: Add all indicators at once
    # ------------------------------------------------------------------
    
    @staticmethod
    def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add ALL technical indicators to the DataFrame.
        
        This is the main method you'll call most of the time.
        It adds 15+ indicators in one shot.
        
        Args:
            df: DataFrame with columns [timestamp, open, high, low, close, volume]
        
        Returns:
            Same DataFrame with additional indicator columns
        """
        df = df.copy()  # Work on copy to avoid modifying original
        
        # --- Ensure timestamp is datetime type ---
        if "timestamp" in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
                df["timestamp"] = pd.to_datetime(df["timestamp"])
        elif df.index.name == "timestamp" or isinstance(df.index, pd.DatetimeIndex):
            # Timestamp is currently the index, reset it to become a column
            df = df.reset_index()
        
        # --- Moving Averages ---
        df = TechnicalIndicators.add_ema(df)
        
        # --- Momentum ---
        df = TechnicalIndicators.add_rsi(df)
        df = TechnicalIndicators.add_macd(df)
        
        # --- Volatility ---
        df = TechnicalIndicators.add_atr(df)
        df = TechnicalIndicators.add_bollinger_bands(df)
        
        # --- Trend Strength ---
        df = TechnicalIndicators.add_adx(df)
        
        # --- Volume ---
        df = TechnicalIndicators.add_volume_indicators(df)
        df = TechnicalIndicators.add_vwap(df)
        
        # --- Support & Resistance ---
        df = TechnicalIndicators.add_swing_levels(df)
        
        return df
    
    # ------------------------------------------------------------------
    # INDICATOR 1: EMA (Exponential Moving Average)
    # ------------------------------------------------------------------
    
    @staticmethod
    def add_ema(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add Exponential Moving Averages.
        
        EMA gives more weight to recent prices, making it more responsive
        than Simple Moving Average (SMA).
        
        Why EMA over SMA?
        - Reacts faster to price changes
        - Better for swing trading entries
        - Most professional traders prefer EMA
        
        Added columns:
        - EMA_20: 20-period EMA (short-term trend)
        - EMA_50: 50-period EMA (medium-term trend)
        - EMA_200: 200-period EMA (long-term trend / bull-bear line)
        """
        df["EMA_20"] = ta.ema(df["close"], length=20)
        df["EMA_50"] = ta.ema(df["close"], length=50)
        df["EMA_200"] = ta.ema(df["close"], length=200)
        
        # EMA slope (is the EMA rising or falling?)
        df["EMA_20_Slope"] = df["EMA_20"].diff(5)  # 5-period change
        df["EMA_50_Slope"] = df["EMA_50"].diff(5)
        
        return df
    
    # ------------------------------------------------------------------
    # INDICATOR 2: RSI (Relative Strength Index)
    # ------------------------------------------------------------------
    
    @staticmethod
    def add_rsi(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
        """
        Add Relative Strength Index.
        
        RSI measures the speed and magnitude of price changes.
        Range: 0 to 100
        
        Traditional interpretation:
        - RSI > 70: Overbought (price may fall soon)
        - RSI < 30: Oversold (price may rise soon)
        - RSI = 50: Neutral
        
        Our strategy uses modified levels:
        - RSI < 35: Buy zone (near oversold, in uptrend)
        - RSI > 65: Sell zone (near overbought)
        
        Why modified levels (35/65 instead of 30/70)?
        In strong trends, RSI rarely reaches 30/70.
        Using 35/65 gives more trading opportunities.
        
        Added columns:
        - RSI: RSI value (0-100)
        - RSI_MA: 14-period moving average of RSI (for smoothing)
        """
        df["RSI"] = ta.rsi(df["close"], length=length)
        df["RSI_MA"] = df["RSI"].rolling(window=length).mean()
        
        return df
    
    # ------------------------------------------------------------------
    # INDICATOR 3: MACD (Moving Average Convergence Divergence)
    # ------------------------------------------------------------------
    
    @staticmethod
    def add_macd(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add MACD indicator.
        
        MACD = 12-period EMA - 26-period EMA (the MACD line)
        Signal = 9-period EMA of MACD (the signal line)
        Histogram = MACD - Signal
        
        Interpretation:
        - MACD crosses above Signal → Bullish (buy signal)
        - MACD crosses below Signal → Bearish (sell signal)
        - Histogram above zero → Bullish momentum
        - Histogram below zero → Bearish momentum
        
        Added columns:
        - MACD: MACD line
        - MACD_Signal: Signal line
        - MACD_Histogram: Difference (MACD - Signal)
        """
        macd_result = ta.macd(df["close"], fast=12, slow=26, signal=9)
        
        # pandas-ta returns a DataFrame with named columns
        # Column names depend on pandas-ta version
        # We handle both common naming conventions
        if "MACD_12_26_9" in macd_result.columns:
            df["MACD"] = macd_result["MACD_12_26_9"]
            df["MACD_Signal"] = macd_result["MACDs_12_26_9"]
            df["MACD_Histogram"] = macd_result["MACDh_12_26_9"]
        else:
            # Fallback: use the first three columns
            df["MACD"] = macd_result.iloc[:, 0]
            df["MACD_Signal"] = macd_result.iloc[:, 1]
            df["MACD_Histogram"] = macd_result.iloc[:, 2]
        
        # MACD crossover detection
        # 1 = bullish crossover, -1 = bearish crossover, 0 = no crossover
        df["MACD_Cross"] = 0
        # Bullish: MACD was below Signal, now above
        df.loc[(df["MACD"] > df["MACD_Signal"]) & 
               (df["MACD"].shift(1) <= df["MACD_Signal"].shift(1)), "MACD_Cross"] = 1
        # Bearish: MACD was above Signal, now below
        df.loc[(df["MACD"] < df["MACD_Signal"]) & 
               (df["MACD"].shift(1) >= df["MACD_Signal"].shift(1)), "MACD_Cross"] = -1
        
        return df
    
    # ------------------------------------------------------------------
    # INDICATOR 4: ATR (Average True Range)
    # ------------------------------------------------------------------
    
    @staticmethod
    def add_atr(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
        """
        Add Average True Range.
        
        ATR measures market volatility, NOT direction.
        It tells you how much price typically moves in one candle.
        
        Why ATR is crucial:
        - Stop Loss should be based on ATR, not arbitrary percentages
        - If ATR is 2%, a 1% stop loss will get hit by normal noise
        - If ATR is 0.5%, a 3% stop loss is too wide
        
        Our stop loss formula: Entry - (ATR × 2.0)
        This means we give the trade 2x normal volatility as breathing room.
        
        Added columns:
        - ATR: Average True Range value
        - ATR_Percent: ATR as percentage of price (for comparison)
        """
        df["ATR"] = ta.atr(df["high"], df["low"], df["close"], length=length)
        df["ATR_Percent"] = (df["ATR"] / df["close"]) * 100
        
        return df
    
    # ------------------------------------------------------------------
    # INDICATOR 5: ADX (Average Directional Index)
    # ------------------------------------------------------------------
    
    @staticmethod
    def add_adx(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
        """
        Add Average Directional Index.
        
        ADX measures trend STRENGTH, not direction.
        Range: 0 to 100
        
        Interpretation:
        - ADX < 20: Weak/Ranging market (avoid trading)
        - ADX 20-40: Trending market (good for our strategy)
        - ADX > 40: Strong trend (may be overextended)
        - ADX > 60: Extremely strong (rare)
        
        Added columns:
        - ADX: Trend strength (0-100)
        - DMP: Plus Directional Movement (bullish pressure)
        - DMN: Minus Directional Movement (bearish pressure)
        """
        adx_result = ta.adx(df["high"], df["low"], df["close"], length=length)
        
        # Handle column names from pandas-ta
        if "ADX_14" in adx_result.columns:
            df["ADX"] = adx_result["ADX_14"]
            df["DMP"] = adx_result["DMP_14"]  # +DI
            df["DMN"] = adx_result["DMN_14"]  # -DI
        else:
            df["ADX"] = adx_result.iloc[:, 0]
            df["DMP"] = adx_result.iloc[:, 1]
            df["DMN"] = adx_result.iloc[:, 2]
        
        # ADX is rising or falling?
        df["ADX_Rising"] = df["ADX"] > df["ADX"].shift(5)
        
        return df
    
    # ------------------------------------------------------------------
    # INDICATOR 6: Bollinger Bands
    # ------------------------------------------------------------------
    
    @staticmethod
    def add_bollinger_bands(
        df: pd.DataFrame, length: int = 20, std: float = 2.0
    ) -> pd.DataFrame:
        """
        Add Bollinger Bands.
        
        Bollinger Bands consist of:
        - Middle Band: 20-period SMA
        - Upper Band: Middle + 2 standard deviations
        - Lower Band: Middle - 2 standard deviations
        
        Interpretation:
        - Price near upper band → May be overextended (sell zone)
        - Price near lower band → May be oversold (buy zone)
        - Narrow bands → Volatility contraction (breakout coming)
        - Wide bands → High volatility
        
        Our use: Confirmation filter. Buy signals are stronger
        when price is near the lower band (oversold condition).
        
        Added columns:
        - BB_Middle: Middle band (SMA 20)
        - BB_Upper: Upper band
        - BB_Lower: Lower band
        - BB_Width: Band width (measure of volatility)
        - BB_Position: Where price is relative to bands (0=lower, 0.5=middle, 1=upper)
        """
        bb_result = ta.bbands(df["close"], length=length, std=std)
        
        # Handle column names
        if f"BBL_{length}_{std}" in bb_result.columns:
            df["BB_Lower"] = bb_result[f"BBL_{length}_{std}"]
            df["BB_Middle"] = bb_result[f"BBM_{length}_{std}"]
            df["BB_Upper"] = bb_result[f"BBU_{length}_{std}"]
        else:
            df["BB_Lower"] = bb_result.iloc[:, 0]
            df["BB_Middle"] = bb_result.iloc[:, 1]
            df["BB_Upper"] = bb_result.iloc[:, 2]
        
        # Additional Bollinger metrics
        df["BB_Width"] = df["BB_Upper"] - df["BB_Lower"]
        df["BB_Width_Percent"] = (df["BB_Width"] / df["BB_Middle"]) * 100
        
        # Where is price within the bands? (0 = at lower, 1 = at upper)
        bb_range = df["BB_Upper"] - df["BB_Lower"]
        df["BB_Position"] = (df["close"] - df["BB_Lower"]) / bb_range
        # Handle division by zero
        df["BB_Position"] = df["BB_Position"].replace([np.inf, -np.inf], 0.5)
        
        return df
    
    # ------------------------------------------------------------------
    # INDICATOR 7: Volume Indicators
    # ------------------------------------------------------------------
    
    @staticmethod
    def add_volume_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add volume-based indicators.
        
        Volume confirms price movements:
        - Price up + High volume = Strong buying (bullish)
        - Price up + Low volume = Weak buying (suspicious)
        - Price down + High volume = Strong selling (bearish)
        - Price down + Low volume = Weak selling (may reverse)
        
        Our use: Volume spike (>1.5x average) validates breakouts
        and confirms that big players are participating.
        
        Added columns:
        - Volume_MA: 20-period average volume
        - Volume_Ratio: Current volume / average volume
        - Volume_Spike: True if Volume_Ratio > 1.5
        """
        df["Volume_MA"] = df["volume"].rolling(window=20).mean()
        df["Volume_Ratio"] = df["volume"] / df["Volume_MA"]
        df["Volume_Spike"] = df["Volume_Ratio"] > 1.5
        
        return df
    
    # ------------------------------------------------------------------
    # INDICATOR 8: VWAP (Volume Weighted Average Price)
    # ------------------------------------------------------------------
    
    @staticmethod
    def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add Volume Weighted Average Price.
        
        VWAP = Sum(Price × Volume) / Sum(Volume)
        
        VWAP is the "true" average price considering volume.
        Institutions use VWAP to measure execution quality.
        
        Our use: Price above VWAP confirms bullish bias.
        If price is below VWAP during a buy signal, it's weaker.
        
        Added columns:
        - VWAP: Volume Weighted Average Price
        - Above_VWAP: True if close > VWAP
        """
        
        # Suppress VWAP warning from pandas-ta
        warnings.filterwarnings("ignore", message=".*VWAP requires.*")

        # VWAP requires DatetimeIndex - set it temporarily
        original_index = None
        if not isinstance(df.index, pd.DatetimeIndex):
            original_index = df.index.copy()
            df = df.copy()
            # Use timestamp column as index for VWAP calculation
            if "timestamp" in df.columns:
                df.set_index("timestamp", inplace=True)
        
        try:
            vwap_series = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
            df["VWAP"] = vwap_series.values if hasattr(vwap_series, 'values') else vwap_series
        except Exception as e:
            log.warning(f"VWAP calculation failed: {e}, using fallback")
            # Fallback: Use simple moving average as proxy for VWAP
            df["VWAP"] = df["close"].rolling(window=20).mean()
        
        # Restore original index if we changed it
        if 'original_index' in locals():
            df.reset_index(inplace=True)
            df.set_index(original_index, inplace=True)
        
        # Fill any NaN VWAP values with close price
        df["VWAP"] = df["VWAP"].fillna(df["close"])
        
        # Above_VWAP check
        df["Above_VWAP"] = df["close"] > df["VWAP"]
        
        return df
    
    # ------------------------------------------------------------------
    # INDICATOR 9: Swing Highs & Lows (Support/Resistance)
    # ------------------------------------------------------------------
    
    @staticmethod
    def add_swing_levels(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
        """
        Detect swing highs and lows (support/resistance levels).
        
        FIXED: Removed center=True (look-ahead bias).
        Now uses expanding/rolling max/min that only looks at PAST data,
        not future candles.
        
        Swing High: Highest high in the last 'window' candles
        Swing Low: Lowest low in the last 'window' candles
        
        Added columns:
        - Swing_High: Recent swing high
        - Swing_Low: Recent swing low
        - Near_Support: True if price within 2% of swing low
        - Near_Resistance: True if price within 2% of swing high
        """
        # FIXED: center=False (default) — only looks at PAST candles
        df["Swing_High"] = df["high"].rolling(window=window, center=False).max()
        df["Swing_Low"] = df["low"].rolling(window=window, center=False).min()
        
        # Forward-fill the levels so they extend until broken
        # This avoids NaN gaps
        df["Swing_High"] = df["Swing_High"].ffill()
        df["Swing_Low"] = df["Swing_Low"].ffill()
        
        # Is price near support/resistance?
        df["Near_Support"] = (df["close"] - df["Swing_Low"]) / df["close"] < 0.02
        df["Near_Resistance"] = (df["Swing_High"] - df["close"]) / df["close"] < 0.02
        
        # Fix NaN values
        df["Near_Support"] = df["Near_Support"].fillna(False)
        df["Near_Resistance"] = df["Near_Resistance"].fillna(False)
        
        return df
    
    # ------------------------------------------------------------------
    # DIVERGENCE DETECTION
    # ------------------------------------------------------------------
    
    @staticmethod
    def detect_divergence(
        df: pd.DataFrame, indicator: str = "RSI", lookback: int = 20
    ) -> pd.DataFrame:
        """
        Detect bullish and bearish divergences.
        
        Bullish Divergence: Price makes lower low, Indicator makes higher low
        → Price may reverse UP (buy signal)
        
        Bearish Divergence: Price makes higher high, Indicator makes lower high
        → Price may reverse DOWN (sell signal)
        
        Divergence is one of the most powerful signals in technical analysis
        because it shows weakening momentum before price reverses.
        
        Args:
            df: DataFrame with price and indicator data
            indicator: Column name of indicator to check (default: "RSI")
            lookback: How many candles to look back
        
        Returns:
            DataFrame with new column '{indicator}_Divergence' (1=bull, -1=bear, 0=none)
        """
        price = df["close"].values
        ind = df[indicator].values
        divergence = np.zeros(len(df))
        
        for i in range(lookback, len(df)):
            # Window of data
            price_window = price[i - lookback : i + 1]
            ind_window = ind[i - lookback : i + 1]
            
            # Find min and max indices in the window
            price_min_idx = np.argmin(price_window)
            ind_min_idx = np.argmin(ind_window)
            price_max_idx = np.argmax(price_window)
            ind_max_idx = np.argmax(ind_window)
            
            # --- Bullish Divergence ---
            # Price is at/near its low for the period
            # But the indicator is NOT at its low
            # (price is weaker than momentum suggests)
            if price_window[-1] <= price_window[price_min_idx] * 1.002:  # within 0.2%
                if ind_window[-1] > ind_window[ind_min_idx]:
                    divergence[i] = 1  # Bullish signal
            
            # --- Bearish Divergence ---
            # Price is at/near its high for the period
            # But the indicator is NOT at its high
            if price_window[-1] >= price_window[price_max_idx] * 0.998:  # within 0.2%
                if ind_window[-1] < ind_window[ind_max_idx]:
                    divergence[i] = -1  # Bearish signal
        
        df[f"{indicator}_Divergence"] = divergence
        return df
    
    # ------------------------------------------------------------------
    # UTILITY: Get latest indicator values
    # ------------------------------------------------------------------
    
    @staticmethod
    def get_latest(df: pd.DataFrame) -> dict:
        """
        Get the most recent values of all indicators.
        
        Useful for quick checks and logging.
        
        Returns:
            Dictionary with latest indicator values
        """
        if df.empty:
            return {}
        
        latest = df.iloc[-1]
        return {
            "close": latest.get("close"),
            "EMA_20": latest.get("EMA_20"),
            "EMA_50": latest.get("EMA_50"),
            "RSI": latest.get("RSI"),
            "MACD": latest.get("MACD"),
            "MACD_Signal": latest.get("MACD_Signal"),
            "ATR": latest.get("ATR"),
            "ATR_Percent": latest.get("ATR_Percent"),
            "ADX": latest.get("ADX"),
            "Volume_Ratio": latest.get("Volume_Ratio"),
            "VWAP": latest.get("VWAP"),
            "Above_VWAP": latest.get("Above_VWAP"),
            "BB_Position": latest.get("BB_Position"),
        }