"""
strategies/base.py

Abstract Base Class for all trading strategies.
Defines the interface that every strategy must implement.

This is the FOUNDATION of our strategy system.
Every strategy inherits from this class.
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any, Tuple
from utils.logger import log


class BaseStrategy(ABC):
    """
    Abstract Base Class for trading strategies.
    
    All strategies MUST implement:
    1. generate_signals() - Main signal logic
    2. validate_signal() - Additional filters
    
    Strategies CAN optionally override:
    - get_stop_loss() - Custom stop loss calculation
    - get_take_profit() - Custom take profit calculation
    """
    
    def __init__(self, name: str, params: Dict[str, Any] = None):
        """
        Initialize the strategy.
        
        Args:
            name: Human-readable strategy name (e.g., "SwingCombo")
            params: Dictionary of strategy parameters
        """
        self.name = name
        self.params = params or {}
        log.debug(f"Strategy '{self.name}' initialized with params: {self.params}")
    
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trading signals from price data.
        
        THIS IS THE CORE METHOD every strategy must implement.
        
        Args:
            df: DataFrame with OHLCV data + indicators
        
        Returns:
            DataFrame with 'signal' column added:
            1 = BUY, -1 = SELL, 0 = HOLD
        """
        pass
    
    @abstractmethod
    def validate_signal(self, df: pd.DataFrame, index: int) -> bool:
        """
        Validate a potential signal with additional filters.
        
        Even if generate_signals() returns a signal,
        this method can reject it based on extra criteria.
        
        Args:
            df: DataFrame with all data
            index: Row index of the potential signal
        
        Returns:
            True if signal is valid, False to reject
        """
        pass
    
    def get_stop_loss(self, df: pd.DataFrame, index: int, entry_price: float) -> float:
        """
        Calculate stop loss price.
        
        Default: 2 ATR below entry.
        Override this method for custom stop loss logic.
        
        Args:
            df: DataFrame with indicators
            index: Entry candle index
            entry_price: Entry price
        
        Returns:
            Stop loss price
        """
        atr = df["ATR"].iloc[index]
        if pd.isna(atr) or atr <= 0:
            # Fallback: 3% below entry
            return entry_price * 0.97
        return entry_price - (atr * 2.0)
    
    def get_take_profit(
        self, entry_price: float, stop_loss: float, rr_ratio: float = 2.5
    ) -> float:
        """
        Calculate take profit price based on risk:reward ratio.
        
        Default: Entry + (Risk × 2.5)
        Risk = Entry - Stop Loss
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            rr_ratio: Risk:Reward ratio (default 2.5)
        
        Returns:
            Take profit price
        """
        risk = abs(entry_price - stop_loss)
        return entry_price + (risk * rr_ratio)
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """
        Get strategy metadata.
        
        Returns:
            Dictionary with strategy name and parameters
        """
        return {
            "name": self.name,
            "params": self.params,
        }