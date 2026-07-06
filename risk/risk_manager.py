"""
risk/risk_manager.py

Risk Management System.
Handles position sizing, daily loss limits, and trade validation.

This is the MOST IMPORTANT module in the entire bot.
Without proper risk management, any strategy will eventually fail.
"""

from typing import Dict, Tuple, Optional
from datetime import datetime, date
from utils.logger import log
from config.settings import (
    PORTFOLIO_SIZE,
    MAX_RISK_PER_TRADE,
    MAX_DAILY_LOSS,
    MAX_OPEN_POSITIONS,
    SL_ATR_MULTIPLIER,
    TP_RISK_REWARD_RATIO,
)


class RiskManager:
    """
    Central risk management system.
    
    Responsibilities:
    1. Position sizing (how much to buy)
    2. Trade validation (should we take this trade?)
    3. Daily loss tracking (stop trading if losing too much)
    4. Portfolio heat management (max concurrent positions)
    5. Stop loss & take profit calculation
    
    Usage:
        rm = RiskManager()
        size = rm.calculate_position_size(entry=62000, stop=60000, balance=1000)
        approved, reason = rm.validate_trade("BTC/USDT", "BUY", 62000, 60000, 2, 15)
    """
    
    def __init__(self):
        """Initialize RiskManager with settings from config."""
        self.portfolio_size = PORTFOLIO_SIZE
        self.max_risk_per_trade = MAX_RISK_PER_TRADE  # 0.02 = 2%
        self.max_daily_loss = MAX_DAILY_LOSS          # 0.05 = 5%
        self.max_open_positions = MAX_OPEN_POSITIONS
        self.sl_atr_multiplier = SL_ATR_MULTIPLIER
        self.tp_rr_ratio = TP_RISK_REWARD_RATIO
        
        # Daily tracking
        self.daily_pnl = 0.0          # Today's profit/loss in USDT
        self.daily_start_balance = PORTFOLIO_SIZE
        self.last_reset_date = date.today()
        
        # Trade tracking
        self.open_positions = []      # List of open position symbols
        
        log.info("RiskManager initialized")
        log.info(f"  Portfolio: ${self.portfolio_size:.0f}")
        log.info(f"  Max Risk/Trade: {self.max_risk_per_trade*100:.1f}%")
        log.info(f"  Max Daily Loss: {self.max_daily_loss*100:.1f}%")
        log.info(f"  Max Positions: {self.max_open_positions}")
    
    # ------------------------------------------------------------------
    # METHOD 1: Calculate Position Size
    # ------------------------------------------------------------------
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float,
        balance: float = None
    ) -> float:
        """
        Calculate how many units to buy based on risk.
        
        Uses Fixed Fractional Position Sizing:
        Position Size = (Portfolio × Risk%) / |Entry - Stop Loss|
        
        Args:
            entry_price: Entry price per unit
            stop_loss_price: Stop loss price per unit
            balance: Current portfolio balance (default: self.portfolio_size)
        
        Returns:
            Quantity to buy (in base currency, e.g., BTC amount)
        
        Example:
            rm = RiskManager()
            qty = rm.calculate_position_size(
                entry_price=62000,   # BTC at $62,000
                stop_loss_price=60000,  # Stop at $60,000
                balance=1000         # $1,000 portfolio
            )
            # Risk = $1000 × 2% = $20
            # Price Risk = $62,000 - $60,000 = $2,000
            # Position = $20 / $2,000 = 0.01 BTC
        """
        if balance is None:
            balance = self.portfolio_size
        
        # Step 1: Calculate dollar risk amount
        risk_amount = balance * self.max_risk_per_trade
        
        # Step 2: Calculate price risk (entry - stop loss distance)
        price_risk = abs(entry_price - stop_loss_price)
        
        # Step 3: Avoid division by zero
        if price_risk == 0:
            log.error("Price risk is zero! Cannot calculate position size.")
            return 0.0
        
        # Step 4: Calculate position size
        position_size = risk_amount / price_risk
        
        # Step 5: Calculate position value
        position_value = position_size * entry_price
        
        # Step 6: Cap position to available balance
        # You can't buy more than your balance allows
        if position_value > balance:
            position_size = balance / entry_price
            log.debug(f"Position capped to balance: {position_size:.6f} units")
        
        log.debug(
            f"Position sizing: Risk=${risk_amount:.2f} | "
            f"Price Risk=${price_risk:.2f} | "
            f"Size={position_size:.6f} units | "
            f"Value=${position_value:.2f}"
        )
        
        return position_size
    
    # ------------------------------------------------------------------
    # METHOD 2: Validate Trade (Pre-Trade Checklist)
    # ------------------------------------------------------------------
    
    def validate_trade(
        self,
        symbol: str,
        signal_type: str,
        entry_price: float,
        stop_loss_price: float,
        open_positions_count: int,
        daily_pnl: float
    ) -> Tuple[bool, str]:
        """
        Pre-trade validation checklist.
        
        Checks ALL risk rules before allowing a trade:
        1. Daily loss limit not exceeded
        2. Maximum positions not exceeded
        3. Not already in this position
        4. Stop loss distance is reasonable
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            signal_type: 'BUY' or 'SELL'
            entry_price: Entry price
            stop_loss_price: Stop loss price
            open_positions_count: Current number of open positions
            daily_pnl: Today's profit/loss so far
        
        Returns:
            (approved: bool, reason: str)
        
        Example:
            approved, reason = rm.validate_trade(
                "BTC/USDT", "BUY", 62000, 60000, 2, -15.0
            )
            # If daily PnL = -$15 (from $1000 = -1.5%), approved=True
            # If daily PnL = -$60 (from $1000 = -6%), approved=False
        """
        # --- Check 1: Daily Loss Limit ---
        self.reset_daily_stats()
        max_daily_loss_amount = self.portfolio_size * self.max_daily_loss
        
        if daily_pnl <= -max_daily_loss_amount:
            reason = (
                f"Daily loss limit reached! "
                f"PnL: ${daily_pnl:.2f} (Limit: -${max_daily_loss_amount:.2f})"
            )
            log.warning(f"Trade rejected: {reason}")
            return False, reason
        
        # --- Check 2: Max Open Positions ---
        if signal_type == "BUY" and open_positions_count >= self.max_open_positions:
            reason = (
                f"Maximum positions ({self.max_open_positions}) already open. "
                f"Current: {open_positions_count}"
            )
            log.warning(f"Trade rejected: {reason}")
            return False, reason
        
        # --- Check 3: Already in position? ---
        if symbol in [p["symbol"] for p in self.open_positions]:
            reason = f"Already holding {symbol}. Close existing position first."
            log.warning(f"Trade rejected: {reason}")
            return False, reason
        
        # --- Check 4: Stop Loss Distance ---
        risk_percent = abs(entry_price - stop_loss_price) / entry_price
        
        # Stop too far (>10% risk in one trade)
        if risk_percent > 0.10:
            reason = f"Stop loss too far: {risk_percent:.1%} from entry (max 10%)"
            log.warning(f"Trade rejected: {reason}")
            return False, reason
        
        # Stop too close (<0.5% - would get stopped by normal noise)
        if risk_percent < 0.005:
            reason = f"Stop loss too close: {risk_percent:.1%} from entry (min 0.5%)"
            log.warning(f"Trade rejected: {reason}")
            return False, reason
        
        # --- All checks passed ---
        log.info(f"Trade validation passed for {symbol}")
        return True, "Trade validated successfully"
    
    # ------------------------------------------------------------------
    # METHOD 3: Daily Stats Reset
    # ------------------------------------------------------------------
    
    def reset_daily_stats(self):
        """
        Reset daily PnL tracking at the start of a new day.
        
        Called automatically by validate_trade().
        """
        today = date.today()
        if today != self.last_reset_date:
            log.info(
                f"New trading day! Resetting daily PnL. "
                f"Yesterday's PnL: ${self.daily_pnl:.2f}"
            )
            self.daily_pnl = 0.0
            self.daily_start_balance = self.portfolio_size
            self.last_reset_date = today
    
    # ------------------------------------------------------------------
    # METHOD 4: Update Portfolio & PnL
    # ------------------------------------------------------------------
    
    def update_pnl(self, trade_pnl: float):
        """
        Update the daily PnL after a trade closes.
        
        Args:
            trade_pnl: Profit/Loss from the closed trade
        """
        self.daily_pnl += trade_pnl
        self.portfolio_size += trade_pnl
        
        log.info(
            f"PnL Updated: Trade=${trade_pnl:+.2f} | "
            f"Daily=${self.daily_pnl:+.2f} | "
            f"Portfolio=${self.portfolio_size:.2f}"
        )
    
    # ------------------------------------------------------------------
    # METHOD 5: Register Open Position
    # ------------------------------------------------------------------
    
    def register_position(self, symbol: str, entry_price: float, stop_loss: float):
        """
        Register a new open position for tracking.
        
        Args:
            symbol: Trading pair
            entry_price: Entry price
            stop_loss: Stop loss price
        """
        self.open_positions.append({
            "symbol": symbol,
            "entry": entry_price,
            "stop_loss": stop_loss,
            "open_time": datetime.now(),
        })
        log.info(f"Position registered: {symbol} (Total open: {len(self.open_positions)})")
    
    # ------------------------------------------------------------------
    # METHOD 6: Remove Closed Position
    # ------------------------------------------------------------------
    
    def remove_position(self, symbol: str):
        """
        Remove a position from tracking when it closes.
        
        Args:
            symbol: Trading pair to remove
        """
        self.open_positions = [
            p for p in self.open_positions if p["symbol"] != symbol
        ]
        log.info(f"Position removed: {symbol} (Total open: {len(self.open_positions)})")
    
    # ------------------------------------------------------------------
    # METHOD 7: Get Portfolio Status
    # ------------------------------------------------------------------
    
    def get_status(self) -> Dict:
        """
        Get current portfolio and risk status.
        
        Returns:
            Dictionary with portfolio metrics
        """
        self.reset_daily_stats()
        
        daily_pnl_pct = (self.daily_pnl / self.daily_start_balance * 100) if self.daily_start_balance > 0 else 0
        
        return {
            "portfolio_size": self.portfolio_size,
            "daily_start_balance": self.daily_start_balance,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_pct": daily_pnl_pct,
            "open_positions": len(self.open_positions),
            "max_positions": self.max_open_positions,
            "positions": [p["symbol"] for p in self.open_positions],
            "daily_loss_limit": self.max_daily_loss * 100,
            "daily_loss_remaining": (self.max_daily_loss * self.daily_start_balance) + self.daily_pnl,
        }
    
    # ------------------------------------------------------------------
    # METHOD 8: Check if Trading is Allowed
    # ------------------------------------------------------------------
    
    def can_trade(self) -> Tuple[bool, str]:
        """
        Master check: Is trading allowed right now?
        
        Checks:
        1. Daily loss limit not exceeded
        2. Maximum positions not exceeded
        
        Returns:
            (can_trade: bool, reason: str)
        """
        self.reset_daily_stats()
        
        # Daily loss check
        max_loss = self.portfolio_size * self.max_daily_loss
        if self.daily_pnl <= -max_loss:
            return False, f"Daily loss limit reached: ${self.daily_pnl:.2f}"
        
        # Max positions check
        if len(self.open_positions) >= self.max_open_positions:
            return False, f"Max positions reached: {len(self.open_positions)}"
        
        return True, "Ready to trade"