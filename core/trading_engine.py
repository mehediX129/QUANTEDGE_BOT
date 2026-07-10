"""
core/trading_engine.py

Central Trading Orchestrator.
Coordinates all modules: data, strategy, risk, execution, tracking.

WHY A SEPARATE ORCHESTRATOR:
- Keeps main.py clean (just entry point)
- Makes testing easier (can test engine without running full bot)
- Single place to understand the trading flow
"""

from datetime import datetime
from utils.logger import log
from config.settings import SYMBOLS, PRIMARY_TIMEFRAME, PORTFOLIO_SIZE, TRADING_MODE
from data.collector import DataCollector
from data.database import Database
from core.position_tracker import PositionTracker
from monitor.telegram_bot import TelegramNotifier


class TradingEngine:
    """Central orchestrator for all trading operations."""
    
    def __init__(self, collector, strategy, risk_manager, executor, 
                 tracker, db, telegram):
        self.collector = collector
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.executor = executor
        self.tracker = tracker
        self.db = db
        self.telegram = telegram
    
    def scan_for_signals(self):
        """Scan all symbols and execute trades."""
        signals_found = []
        
        log.info("=" * 50)
        log.info(f"SIGNAL SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.info("=" * 50)
        
        self.tracker.reset_daily_if_needed()
        daily_pnl = self.tracker.get_daily_pnl()
        open_count = self.tracker.get_open_positions_count()
        
        log.info(f"Open Positions: {open_count} | Daily PnL: ${daily_pnl:+.2f}")
        
        for symbol in SYMBOLS:
            # Per-asset timeframe (research-backed)
            from config.settings import ASSET_TIMEFRAMES
            asset_timeframe = ASSET_TIMEFRAMES.get(symbol, PRIMARY_TIMEFRAME)
            df = self.collector.fetch_ohlcv(symbol, timeframe=asset_timeframe, limit=200)
            if df is None or len(df) < 50:
                continue
            
            df = self.strategy.generate_signals(df)
            latest_signal = df["signal"].iloc[-1]
            latest = df.iloc[-1]
            close = latest["close"]
            candle_time = df["timestamp"].iloc[-1]
            
            rsi = latest.get("RSI", None)
            adx = latest.get("ADX", None)
            vol = latest.get("Volume_Ratio", None)
            rsi_str = f"RSI={rsi:.1f}" if rsi is not None else "RSI=N/A"
            adx_str = f"ADX={adx:.1f}" if adx is not None else "ADX=N/A"
            vol_str = f"Vol={vol:.1f}x" if vol is not None else "Vol=N/A"
            
            # BUY
            if latest_signal == 1:
                self._handle_buy(symbol, df, latest, close, candle_time, 
                            rsi_str, adx_str, vol_str, signals_found)
            # SELL
            elif latest_signal == -1:
                self._handle_sell(symbol, latest, close, candle_time,
                                 rsi_str, adx_str, vol_str, signals_found)
            # HOLD
            else:
                trend = "↗" if latest.get("EMA_20", 0) > latest.get("EMA_50", 0) else "↘"
                pos_marker = " 🔒" if self.tracker.is_in_position(symbol) else ""
                log.info(f"⚪ HOLD {symbol:<12} ${close:>10,.2f} | {rsi_str} | {adx_str} | {vol_str} | {trend}{pos_marker}")
        
        buy_count = sum(1 for s in signals_found if s["signal"] == "BUY")
        sell_count = sum(1 for s in signals_found if s["signal"] == "SELL")
        executed = sum(1 for s in signals_found if s.get("executed"))
        
        log.info(f"SUMMARY: {buy_count} Buy ({executed} executed) | {sell_count} Sell | "
                f"Open: {self.tracker.get_open_positions_count()}")
        log.info("=" * 50)
        
        # Save equity snapshot
        self.db.save_equity_snapshot(
            PORTFOLIO_SIZE + self.tracker.get_daily_pnl(),
            self.tracker.get_daily_pnl(),
            self.tracker.get_open_positions_count()
        )
        
        return signals_found
    
    def _handle_buy(self, symbol, df, latest, close, candle_time, 
                    rsi_str, adx_str, vol_str, signals_found):

        """Handle BUY signal."""
        if self.tracker.is_duplicate_signal(symbol, "BUY", candle_time):
            return
        if self.tracker.is_in_position(symbol):
            log.info(f"⚪ {symbol}: Already in position")
            return
        
        entry_price = close
        stop_loss = self.strategy.get_stop_loss(df, len(df)-1, entry_price)
        take_profit = self.strategy.get_take_profit(entry_price, stop_loss)
        
        # Risk validation
        approved, reason = self.risk_manager.validate_trade(
            symbol=symbol,
            signal_type="BUY",
            entry_price=entry_price,
            stop_loss_price=stop_loss,
        )
        
        if not approved:
            log.warning(f"🔵 BUY {symbol} REJECTED: {reason}")
            self.db.save_signal(symbol, "BUY", close, 
                              latest.get("RSI"), latest.get("ADX"),
                              latest.get("Volume_Ratio"),
                              "UPTREND" if latest.get("EMA_20", 0) > latest.get("EMA_50", 0) else "DOWN",
                              candle_time, False, reason)
            return
        
        qty = self.risk_manager.calculate_position_size(entry_price, stop_loss, PORTFOLIO_SIZE)
        
        log.success(f"🔵 BUY  {symbol:<12} ${close:>10,.2f} | {rsi_str} | {adx_str} | {vol_str}")
        log.info(f"     Entry=${entry_price:,.2f} | SL=${stop_loss:,.2f} | TP=${take_profit:,.2f} | Size={qty:.6f}")
        
        order = None
        if TRADING_MODE == "paper":
            order = self.executor.market_buy(symbol, qty)
            if order:
                self.tracker.open_position(symbol, entry_price, qty, stop_loss, take_profit)
                self.risk_manager.register_position(symbol, entry_price, stop_loss)
                trade_id = self.db.save_trade(symbol, "BUY", qty, entry_price)
                self.db.save_signal(symbol, "BUY", close,
                                  latest.get("RSI"), latest.get("ADX"),
                                  latest.get("Volume_Ratio"),
                                  "UPTREND", candle_time, True, "Executed")
                self.telegram.trade_alert(symbol, "BUY", qty, entry_price)
        
        signals_found.append({
            "symbol": symbol, "signal": "BUY", "entry": entry_price,
            "stop_loss": stop_loss, "take_profit": take_profit,
            "qty": qty, "executed": order is not None,
        })
    
    def _handle_sell(self, symbol, latest, close, candle_time,
                     rsi_str, adx_str, vol_str, signals_found):
        """Handle SELL signal."""
        if not self.tracker.is_in_position(symbol):
            return
        if self.tracker.is_duplicate_signal(symbol, "SELL", candle_time):
            return
        
        pos = self.tracker.get_position(symbol)
        log.warning(f"🔴 SELL {symbol:<12} ${close:>10,.2f} | {rsi_str} | {adx_str} | {vol_str}")
        
        order = None
        if TRADING_MODE == "paper":
            order = self.executor.market_sell(symbol, pos["quantity"])
            if order:
                pnl = self.tracker.close_position(symbol, close)
                self.risk_manager.remove_position(symbol)
                self.risk_manager.update_pnl(pnl)
                
                # Close in DB
                for trade in self.db.get_open_trades():
                    if trade["symbol"] == symbol:
                        self.db.close_trade(trade["id"], close, pnl)
                
                self.db.save_signal(symbol, "SELL", close,
                                  latest.get("RSI"), latest.get("ADX"),
                                  latest.get("Volume_Ratio"),
                                  "DOWN", candle_time, True, f"PnL=${pnl:+.2f}")
                self.telegram.trade_alert(symbol, "SELL", pos["quantity"], close)
        
        signals_found.append({
            "symbol": symbol, "signal": "SELL", "executed": order is not None,
        })