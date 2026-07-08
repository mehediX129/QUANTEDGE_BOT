"""
data/database.py

SQLite Database Module.
Stores all trading history persistently.

TABLES:
- trades: Every executed trade (entry, exit, PnL)
- signals: Every signal generated (BUY/SELL/HOLD with indicator values)
- equity_snapshots: Daily portfolio value snapshots

WHY SQLITE:
- Zero setup (no server needed, just a file)
- Perfect for single-user trading bot
- Can migrate to PostgreSQL later if needed
- Built into Python (no extra dependencies)
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from utils.logger import log


class Database:
    """
    SQLite database manager for trade history.
    
    Usage:
        db = Database()
        db.save_trade(symbol, side, qty, price, pnl)
        trades = db.get_trades(limit=20)
    """
    
    def __init__(self, db_path: str = None):
        """Initialize database connection and create tables."""
        if db_path is None:
            root = Path(__file__).parent.parent
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = data_dir / "trading_data.db"
        else:
            self.db_path = Path(db_path)
        
        self.conn = sqlite3.connect(str(self.db_path))
        self._create_tables()
        log.info(f"Database connected: {self.db_path}")
    
    def _create_tables(self):
        """Create all tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                pnl REAL DEFAULT 0,
                pnl_percent REAL DEFAULT 0,
                status TEXT DEFAULT 'open',
                strategy TEXT DEFAULT 'swing_combo',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                price REAL NOT NULL,
                rsi REAL,
                adx REAL,
                volume_ratio REAL,
                ema_trend TEXT,
                candle_time TEXT,
                executed INTEGER DEFAULT 0,
                reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Equity snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                equity REAL NOT NULL,
                daily_pnl REAL DEFAULT 0,
                open_positions INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
        log.debug("Database tables ready")
    
    # ------------------------------------------------------------------
    # TRADE METHODS
    # ------------------------------------------------------------------
    
    def save_trade(self, symbol: str, side: str, quantity: float, 
                   entry_price: float) -> int:
        """Save a new trade (entry). Returns trade ID."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO trades (symbol, side, quantity, entry_price, entry_time, status)
            VALUES (?, ?, ?, ?, ?, 'open')
        """, (symbol, side, quantity, entry_price, datetime.now().isoformat()))
        self.conn.commit()
        trade_id = cursor.lastrowid
        log.info(f"💾 Trade #{trade_id} saved: {side} {quantity} {symbol} @ ${entry_price:.2f}")
        return trade_id
    
    def close_trade(self, trade_id: int, exit_price: float, pnl: float):
        """Close a trade with exit price and PnL."""
        if trade_id == 0:
            # Trade was never saved (paper mode without DB)
            return
        
        pnl_percent = (pnl / (exit_price * 1)) * 100  # Approximate
        
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE trades 
            SET exit_price = ?, exit_time = ?, pnl = ?, pnl_percent = ?, status = 'closed'
            WHERE id = ?
        """, (exit_price, datetime.now().isoformat(), pnl, pnl_percent, trade_id))
        self.conn.commit()
        log.info(f"💾 Trade #{trade_id} closed: PnL=${pnl:+.2f}")
    
    def get_open_trades(self) -> List[Dict]:
        """Get all currently open trades."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE status = 'open'")
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_trade_history(self, limit: int = 20) -> List[Dict]:
        """Get recent trade history."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM trades 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    # ------------------------------------------------------------------
    # SIGNAL METHODS
    # ------------------------------------------------------------------
    
    def save_signal(self, symbol: str, signal: str, price: float,
                    rsi: float = None, adx: float = None, 
                    volume_ratio: float = None, ema_trend: str = None,
                    candle_time: str = None, executed: bool = False,
                    reason: str = None):
        """Save a trading signal."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO signals (symbol, signal, price, rsi, adx, volume_ratio,
                                ema_trend, candle_time, executed, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, signal, price, rsi, adx, volume_ratio, 
              ema_trend, str(candle_time) if candle_time else None,
              1 if executed else 0, reason))
        self.conn.commit()
    
    # ------------------------------------------------------------------
    # EQUITY METHODS
    # ------------------------------------------------------------------
    
    def save_equity_snapshot(self, equity: float, daily_pnl: float, 
                             open_positions: int):
        """Save daily equity snapshot (upsert)."""
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO equity_snapshots (date, equity, daily_pnl, open_positions)
            VALUES (?, ?, ?, ?)
        """, (today, equity, daily_pnl, open_positions))
        self.conn.commit()
    
    # ------------------------------------------------------------------
    # STATS METHODS
    # ------------------------------------------------------------------
    
    def get_stats(self) -> Dict:
        """Get overall trading statistics."""
        cursor = self.conn.cursor()
        
        # Total trades
        cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'closed'")
        total_trades = cursor.fetchone()[0]
        
        # Winning trades
        cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'closed' AND pnl > 0")
        winning = cursor.fetchone()[0]
        
        # Total PnL
        cursor.execute("SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status = 'closed'")
        total_pnl = cursor.fetchone()[0]
        
        win_rate = (winning / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "total_trades": total_trades,
            "winning_trades": winning,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
        }
    
    def close(self):
        """Close database connection."""
        self.conn.close()
        log.debug("Database connection closed")