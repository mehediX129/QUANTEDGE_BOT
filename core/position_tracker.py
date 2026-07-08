"""
core/position_tracker.py

Position State Manager.
Persists trading state between scan cycles using a JSON file.

WHY JSON (not SQLite yet):
- Simple, human-readable, no dependencies
- Easy to debug (just open the file)
- Perfect for paper trading phase
- SQLite will come in Phase 3 for full trade history

WHAT IT TRACKS:
- Currently open positions (symbol, entry, qty, SL, TP)
- Last signal per symbol (prevents duplicate alerts)
- Daily PnL
"""

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Optional
from utils.logger import log


class PositionTracker:
    """
    Tracks open positions and trade state across scan cycles.
    
    State file location: data/positions.json
    
    Usage:
        tracker = PositionTracker()
        tracker.open_position("BTC/USDT", 62000, 0.01, 60000, 65000)
        is_open = tracker.is_in_position("BTC/USDT")
        tracker.close_position("BTC/USDT", 63000)
    """
    
    def __init__(self, state_file: str = None):
        """Initialize tracker and load existing state."""
        if state_file is None:
            root = Path(__file__).parent.parent
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.state_file = data_dir / "positions.json"
        else:
            self.state_file = Path(state_file)
        
        self.state = self._load_state()
        log.debug(f"PositionTracker initialized | Open positions: {len(self.state.get('positions', {}))}")
    
    def _load_state(self) -> Dict:
        """Load state from JSON file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                log.warning(f"Failed to load state file: {e}. Starting fresh.")
        
        return {
            "positions": {},       # {symbol: {entry, qty, sl, tp, entry_time}}
            "last_signals": {},     # {symbol: {signal, timestamp, candle_time}}
            "daily_pnl": 0.0,
            "daily_start_balance": 1000.0,
            "last_reset_date": str(date.today()),
        }
    
    def _save_state(self):
        """Save state to JSON file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
        except IOError as e:
            log.error(f"Failed to save state: {e}")
    
    # ------------------------------------------------------------------
    # Position Management
    # ------------------------------------------------------------------
    
    def open_position(self, symbol: str, entry_price: float, qty: float,
                      stop_loss: float, take_profit: float):
        """Record a new open position."""
        self.state["positions"][symbol] = {
            "entry_price": entry_price,
            "quantity": qty,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_time": datetime.now().isoformat(),
        }
        self._save_state()
        log.info(f"📝 Position OPENED: {symbol} | Entry=${entry_price:.2f} | Qty={qty:.6f}")
    
    def close_position(self, symbol: str, exit_price: float):
        """Close a position and calculate PnL."""
        if symbol not in self.state["positions"]:
            log.warning(f"Cannot close {symbol}: not in position")
            return 0.0
        
        pos = self.state["positions"][symbol]
        pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
        
        self.state["daily_pnl"] += pnl
        del self.state["positions"][symbol]
        self._save_state()
        
        log.info(f"📝 Position CLOSED: {symbol} | Exit=${exit_price:.2f} | PnL=${pnl:+.2f}")
        return pnl
    
    def is_in_position(self, symbol: str) -> bool:
        """Check if we already hold a position in this symbol."""
        return symbol in self.state["positions"]
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position details for a symbol."""
        return self.state["positions"].get(symbol)
    
    def get_open_positions_count(self) -> int:
        """Number of currently open positions."""
        return len(self.state["positions"])
    
    def get_open_symbols(self) -> list:
        """List of symbols we currently hold."""
        return list(self.state["positions"].keys())
    
    # ------------------------------------------------------------------
    # Signal Tracking (Prevents Duplicate Alerts)
    # ------------------------------------------------------------------
    
    def is_duplicate_signal(self, symbol: str, signal: str, candle_time) -> bool:
        """
        Check if this signal was already triggered for the same candle.
        
        A 4H candle lasts 4 hours. If the scanner runs every 15 minutes,
        the same candle will be scanned 16+ times. Without this check,
        we'd get duplicate BUY alerts for the same signal.
        
        Args:
            symbol: Trading pair
            signal: 'BUY' or 'SELL'
            candle_time: Timestamp of the current candle
        
        Returns:
            True if this is a duplicate, False if new signal
        """
        last = self.state["last_signals"].get(symbol, {})
        
        if (last.get("signal") == signal and 
            str(candle_time) == last.get("candle_time")):
            log.debug(f"Duplicate {signal} for {symbol} at {candle_time} — skipped")
            return True
        
        # Record this signal
        self.state["last_signals"][symbol] = {
            "signal": signal,
            "timestamp": datetime.now().isoformat(),
            "candle_time": str(candle_time),
        }
        self._save_state()
        return False
    
    # ------------------------------------------------------------------
    # Daily Reset
    # ------------------------------------------------------------------
    
    def reset_daily_if_needed(self):
        """Reset daily PnL at start of new day."""
        today = str(date.today())
        if self.state.get("last_reset_date") != today:
            log.info(f"New trading day! Resetting daily PnL.")
            self.state["daily_pnl"] = 0.0
            self.state["last_reset_date"] = today
            self._save_state()
    
    def get_daily_pnl(self) -> float:
        """Get today's PnL."""
        self.reset_daily_if_needed()
        return self.state["daily_pnl"]
    
    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    
    def get_status(self) -> Dict:
        """Get full status summary."""
        self.reset_daily_if_needed()
        return {
            "open_positions": len(self.state["positions"]),
            "symbols": list(self.state["positions"].keys()),
            "daily_pnl": self.state["daily_pnl"],
            "positions": self.state["positions"],
        }