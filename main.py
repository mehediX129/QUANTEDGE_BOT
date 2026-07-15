"""
main.py — QuantEdge Continuous Market Scanner

Entry point for QuantEdge Trading Bot.
Scans all configured symbols every 15 minutes for trading signals
using the Multi-Timeframe EMA+RSI+Volume Confluence Strategy.

Run command:
    python main.py

Stop command:
    Ctrl + C

What this file does:
    1. Initializes exchange connection (Binance Testnet or Live)
    2. Loads the SwingCombo trading strategy
    3. Initializes Risk Manager for position sizing
    4. Scans all configured symbols for BUY/SELL signals
    5. Repeats scan every 15 minutes automatically
    6. Displays compact one-line status per symbol
    7. Shows Entry, Stop Loss, Take Profit, Position Size for BUY signals
"""

import sys
import time
from datetime import datetime
from pathlib import Path

# ------------------------------------------------------------------
# PATH SETUP
# ------------------------------------------------------------------
# Add the project root folder to Python's search path.
# This ensures 'from utils.logger import log' works from any folder.
# __file__ = D:\Projects\quantedge_bot\main.py
# .parent  = D:\Projects\quantedge_bot\  (project root)
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# ------------------------------------------------------------------
# PROJECT IMPORTS
# ------------------------------------------------------------------
# Our own modules — each serves a specific purpose:
from utils.logger import log              # Professional logging (loguru)
from config.settings import (
    TRADING_MODE,
    SYMBOLS,
    PORTFOLIO_SIZE,
    PRIMARY_TIMEFRAME,
    SYMBOL_STRATEGY_MAP,
)
from data.collector import DataCollector  # Exchange connection & data fetching
from strategies import DEFAULT_STRATEGY, STRATEGIES  # Strategy registry
from risk.risk_manager import RiskManager # Risk management & position sizing
from execution.order_executor import OrderExecutor
from core.position_tracker import PositionTracker
from monitor.telegram_bot import TelegramNotifier
from data.database import Database

# ==================================================================
# FUNCTION 1: display_startup_banner()
# ==================================================================

def display_startup_banner():
    """
    Display a formatted ASCII banner showing bot configuration.
    
    This is purely cosmetic — it helps you verify at a glance:
    - Which mode the bot is running in (paper/live)
    - How much virtual capital is allocated
    - Which symbols are being scanned
    - Which strategy is loaded
    - When the bot was started
    """
    banner = f"""
╔══════════════════════════════════════════════╗
║     QUANTEDGE CONTINUOUS MARKET SCANNER     ║
╠══════════════════════════════════════════════╣
║  Mode:      {TRADING_MODE:<30} ║
║  Portfolio: ${PORTFOLIO_SIZE:<29} ║
║  Symbols:   {', '.join(SYMBOLS[:2])}{'...' if len(SYMBOLS) > 2 else '':<30} ║
║  Timeframe: {PRIMARY_TIMEFRAME:<30} ║
║  Strategy:  {DEFAULT_STRATEGY:<30} ║
║  Scan Every: 15 minutes                   ║
║  Started:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<30} ║
╚══════════════════════════════════════════════╝
"""
    print(banner)


# ==================================================================
# FUNCTION 2: scan_for_signals()
# ==================================================================

def scan_for_signals(collector, strategies, risk_manager, executor, tracker, telegram, db):
    """
    Scan ALL symbols for signals, validate, and execute paper trades.
    """
    signals_found = []
    
    log.info("=" * 50)
    log.info(f"SIGNAL SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 50)
    
    # Reset daily tracking if new day
    tracker.reset_daily_if_needed()
    daily_pnl = tracker.get_daily_pnl()
    open_count = tracker.get_open_positions_count()
    
    log.info(f"Open Positions: {open_count} | Daily PnL: ${daily_pnl:+.2f}")
    
    for symbol in SYMBOLS:
        # Fetch data
        # Per-asset timeframe (research-backed)
        from config.settings import ASSET_TIMEFRAMES
        asset_timeframe = ASSET_TIMEFRAMES.get(symbol, PRIMARY_TIMEFRAME)
        df = collector.fetch_ohlcv(symbol, timeframe=asset_timeframe, limit=200)

        if df is None or len(df) < 50:
            continue
        
        # Generate signals
        # Get the right strategy for this symbol
        symbol_strategy = strategies.get(symbol, list(strategies.values())[0])
        df = symbol_strategy.generate_signals(df)

        latest_signal = df["signal"].iloc[-1]
        latest = df.iloc[-1]
        close = latest["close"]
        candle_time = df["timestamp"].iloc[-1]
        
        rsi = latest.get("RSI", None)
        adx = latest.get("ADX", None)
        vol = latest.get("Volume_Ratio", None)
        rsi_str = f"RSI={rsi:.1f}" if rsi is not None and not (isinstance(rsi, float) and str(rsi) == 'nan') else "RSI=N/A"
        adx_str = f"ADX={adx:.1f}" if adx is not None and not (isinstance(adx, float) and str(adx) == 'nan') else "ADX=N/A"
        vol_str = f"Vol={vol:.1f}x" if vol is not None and not (isinstance(vol, float) and str(vol) == 'nan') else "Vol=N/A"
        
        # --- BUY SIGNAL ---
        if latest_signal == 1:
            # Skip if duplicate
            if tracker.is_duplicate_signal(symbol, "BUY", candle_time):
                continue
            
            # Skip if already in position
            if tracker.is_in_position(symbol):
                log.info(f"⚪ {symbol}: Already in position, skipping BUY")
                continue
            
            entry_price = close
            stop_loss = symbol_strategy.get_stop_loss(df, len(df)-1, entry_price)
            take_profit = symbol_strategy.get_take_profit(entry_price, stop_loss)
            
            # --- RISK VALIDATION ---
            approved, reason = risk_manager.validate_trade(
                symbol=symbol,
                signal_type="BUY",
                entry_price=entry_price,
                stop_loss_price=stop_loss,
            )
            
            if not approved:
                log.warning(f"🔵 BUY {symbol} REJECTED: {reason}")
                continue
            
            # --- POSITION SIZING ---
            qty = risk_manager.calculate_position_size(entry_price, stop_loss, PORTFOLIO_SIZE)
            
            log.success(f"🔵 BUY  {symbol:<12} ${close:>10,.2f} | {rsi_str} | {adx_str} | {vol_str}")
            log.info(f"     Entry=${entry_price:,.2f} | SL=${stop_loss:,.2f} | TP=${take_profit:,.2f} | Size={qty:.6f}")
            
            # --- EXECUTE PAPER ORDER ---
            order = None
            if TRADING_MODE == "paper":
                order = executor.market_buy(symbol, qty)
                if order:
                    # Track position
                    tracker.open_position(symbol, entry_price, qty, stop_loss, take_profit)
                    risk_manager.register_position(symbol, entry_price, stop_loss)
                    open_count += 1
                    # Telegram
                    telegram.trade_alert(symbol, "BUY", qty, entry_price)

            signals_found.append({
                "symbol": symbol, "signal": "BUY",
                "entry": entry_price, "stop_loss": stop_loss,
                "take_profit": take_profit, "qty": qty,
                "executed": order is not None,
            })
        
        # --- SELL SIGNAL ---
        elif latest_signal == -1:
            if not tracker.is_in_position(symbol):
                continue
            
            if tracker.is_duplicate_signal(symbol, "SELL", candle_time):
                continue
            
            pos = tracker.get_position(symbol)
            
            log.warning(f"🔴 SELL {symbol:<12} ${close:>10,.2f} | {rsi_str} | {adx_str} | {vol_str}")
            
            # Execute paper sell
            order = None
            if TRADING_MODE == "paper":
                order = executor.market_sell(symbol, pos["quantity"])
                if order:
                    pnl = tracker.close_position(symbol, close)
                    risk_manager.remove_position(symbol)
                    risk_manager.update_pnl(pnl)
                    open_count -= 1
                    telegram.trade_alert(symbol, "SELL", pos["quantity"], close)
                    
                    # Save to database
                    trade_id = db.save_trade(symbol, "SELL", pos["quantity"], close)
                    db.save_signal(symbol, "SELL", close, rsi, adx, vol, 
                                  "UPTREND" if latest.get("EMA_20", 0) > latest.get("EMA_50", 0) else "DOWN",
                                  candle_time, True, "Risk approved")
            
            signals_found.append({
                "symbol": symbol, "signal": "SELL", "executed": order is not None,
            })
        
        # --- HOLD ---
        else:
            trend = "↗" if latest.get("EMA_20", 0) > latest.get("EMA_50", 0) else "↘"
            pos_marker = " 🔒" if tracker.is_in_position(symbol) else ""
            log.info(f"⚪ HOLD {symbol:<12} ${close:>10,.2f} | {rsi_str} | {adx_str} | {vol_str} | {trend}{pos_marker}")
    
    # Summary
    buy_count = sum(1 for s in signals_found if s["signal"] == "BUY")
    sell_count = sum(1 for s in signals_found if s["signal"] == "SELL")
    executed_buys = sum(1 for s in signals_found if s["signal"] == "BUY" and s.get("executed"))
    
    log.info(f"SUMMARY: {buy_count} Buy ({executed_buys} executed) | {sell_count} Sell | "
             f"Open: {tracker.get_open_positions_count()}")
    log.info("=" * 50)
    
    return signals_found

# ==================================================================
# FUNCTION 3: test_order_executor()
# ==================================================================

def test_order_executor():
    """
    Test the Order Executor with a small paper trade.
    
    This function:
    1. Creates an OrderExecutor instance
    2. Checks account balance
    3. Checks BTC price
    4. Calculates minimum buyable quantity
    5. Does NOT actually place an order (safety first)
    
    Run separately: python -c "from main import test_order_executor; test_order_executor()"
    """
    from execution.order_executor import OrderExecutor
    
    log.info("=" * 50)
    log.info("ORDER EXECUTOR TEST")
    log.info("=" * 50)
    
    executor = OrderExecutor()
    
    # Test 1: Get Balance
    usdt_balance = executor.get_balance("USDT")
    log.info(f"📊 USDT Balance: ${usdt_balance:.2f}")
    
    # Test 2: Get Price
    btc_price = executor.get_current_price("BTC/USDT")
    log.info(f"📊 BTC Price: ${btc_price:,.2f}")
    
    # Test 3: Symbol Info
    info = executor._get_symbol_info("BTC/USDT")
    log.info(f"📊 BTC/USDT Info:")
    log.info(f"    Min Amount: {info['min_amount']}")
    log.info(f"    Min Notional: ${info['min_notional']}")
    log.info(f"    Amount Precision: {info['amount_precision']}")
    
    # Test 4: Calculate minimum buy
    if btc_price and usdt_balance:
        min_btc = info['min_notional'] / btc_price
        log.info(f"📊 Minimum BTC buyable: {min_btc:.6f} BTC")
        log.info(f"📊 Maximum BTC buyable: {(usdt_balance * 0.98 / btc_price):.6f} BTC")
    
    # Test 5: Quantity rounding
    raw_qty = 0.123456789
    rounded = executor._round_quantity(raw_qty, info['amount_precision'])
    log.info(f"📊 Rounding test: {raw_qty} → {rounded}")
    
    log.info("=" * 50)
    log.info("ORDER EXECUTOR TEST COMPLETE")
    log.info("=" * 50)

# ==================================================================
# FUNCTION 4: main()
# ==================================================================

def main():
    """
    Main entry point for the trading bot.
    
    Execution flow:
    1. Display startup banner
    2. Initialize DataCollector (exchange connection)
    3. Initialize Strategy (signal generation logic)
    4. Initialize RiskManager (position sizing)
    5. Run first market scan immediately
    6. Enter continuous loop — scan every 15 minutes
    7. On Ctrl+C, graceful shutdown
    """
    
    # ------------------------------------------------------------------
    # STEP 1: Show startup banner
    # ------------------------------------------------------------------
    display_startup_banner()
    
    # ------------------------------------------------------------------
    # STEP 2: Log system configuration
    # ------------------------------------------------------------------
    log.info("=" * 50)
    log.info("QUANTEDGE BOT — INITIALIZING")
    log.info(f"Mode: {TRADING_MODE} | Portfolio: ${PORTFOLIO_SIZE}")
    log.info(f"Symbols: {SYMBOLS}")
    log.info(f"Timeframe: {PRIMARY_TIMEFRAME}")
    log.info(f"Strategy: {DEFAULT_STRATEGY}")
    log.info("=" * 50)
    
    # ------------------------------------------------------------------
    # STEP 3: Validate configuration
    # ------------------------------------------------------------------
    if not SYMBOLS:
        log.error("No symbols configured! Add symbols in config/settings.py")
        sys.exit(1)
    
    log.success("Configuration validated")
    
    # ------------------------------------------------------------------
    # STEP 4: Initialize DataCollector
    # ------------------------------------------------------------------
    log.info("Connecting to exchange...")
    try:
        collector = DataCollector()
        log.success(f"Exchange connected ({TRADING_MODE} mode)")
    except Exception as e:
        log.error(f"Exchange connection failed: {e}")
        log.error("Check: 1) API keys in .env  2) Internet connection  3) Binance status")
        sys.exit(1)
    
    # ------------------------------------------------------------------
    # STEP 5: Quick health check
    # ------------------------------------------------------------------
    if not collector.check_exchange_status():
        log.error("Exchange appears offline. Exiting.")
        sys.exit(1)
    
    # ------------------------------------------------------------------
    # STEP 6: Initialize Strategy
    # ------------------------------------------------------------------
    log.info(f"Loading strategy: {DEFAULT_STRATEGY}")
    StrategyClass = STRATEGIES.get(DEFAULT_STRATEGY)
    if StrategyClass is None:
        log.error(f"Strategy '{DEFAULT_STRATEGY}' not found in registry!")
        log.error(f"Available strategies: {list(STRATEGIES.keys())}")
        sys.exit(1)
    
        # Per-asset strategy loading (research-backed)
    asset_strategies = {}
    for symbol in SYMBOLS:
        strategy_name = SYMBOL_STRATEGY_MAP.get(symbol, DEFAULT_STRATEGY)
        StrategyClass = STRATEGIES.get(strategy_name)
        if StrategyClass:
            asset_strategies[symbol] = StrategyClass()
            log.success(f"  {symbol}: {strategy_name} loaded")
        else:
            log.error(f"Strategy '{strategy_name}' not found for {symbol}")
            sys.exit(1)
    
    # ------------------------------------------------------------------
    # STEP 7: Initialize Risk Manager
    # ------------------------------------------------------------------
    risk_manager = RiskManager()
    log.success("Risk Manager initialized")
    
    # ------------------------------------------------------------------
    # STEP 8: Initialize Order Executor + Position Tracker + Telegram
    # ------------------------------------------------------------------
    executor = OrderExecutor()
    log.success("Order Executor initialized")
    
    tracker = PositionTracker()
    log.success(f"Position Tracker initialized ({tracker.get_open_positions_count()} open)")
    
    # DATABASE
    db = Database()
    log.success("Database initialized")

    telegram = TelegramNotifier()
    if telegram.enabled:
        telegram.send(f"🤖 <b>QuantEdge Bot Started</b>\n"
                      f"Mode: {TRADING_MODE}\n"
                      f"Portfolio: ${PORTFOLIO_SIZE}\n"
                      f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ------------------------------------------------------------------
    # STEP 9: All systems go — run first scan
    # ------------------------------------------------------------------
    log.info("")
    log.info("🚀 All systems initialized. Running first market scan...")
    log.info("")
    
    scan_for_signals(collector, asset_strategies, risk_manager, executor, tracker, telegram, db)
    
    # ------------------------------------------------------------------
    # STEP 10: Continuous scanning loop
    # ------------------------------------------------------------------
    SCAN_INTERVAL_MINUTES = 5  # Scan every 5 minutes
    
    log.info("")
    log.info(f"🔄 Continuous mode active — scanning every {SCAN_INTERVAL_MINUTES} minutes")
    log.info("   Press Ctrl+C to stop the bot")
    log.info("")
    
    try:
        while True:
            # ----------------------------------------------------------
            # Countdown timer with debug heartbeat every 5 minutes
            # ----------------------------------------------------------
            for minute in range(SCAN_INTERVAL_MINUTES):
                time.sleep(60)  # Sleep 1 minute
                
                # Every 5 minutes, log remaining time
                if minute % 5 == 0 and minute > 0:
                    remaining = SCAN_INTERVAL_MINUTES - minute
                    log.debug(f"⏳ Next scan in {remaining} minutes...")
            
            # ----------------------------------------------------------
            # Time to scan!
            # ----------------------------------------------------------
            scan_for_signals(collector, asset_strategies, risk_manager, executor, tracker, telegram, db)
            
            # Save daily equity snapshot
            db.save_equity_snapshot(
                PORTFOLIO_SIZE + tracker.get_daily_pnl(),
                tracker.get_daily_pnl(),
                tracker.get_open_positions_count()
            )
            
            print()  # Blank line between scans for readability
    
    # ------------------------------------------------------------------
    # STEP 11: Graceful shutdown
    # ------------------------------------------------------------------
    except KeyboardInterrupt:
        log.info("")
        log.info("=" * 50)
        log.info("SHUTTING DOWN")
        log.info(f"Bot stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.info("Goodbye!")
        log.info("=" * 50)
        sys.exit(0)


# ==================================================================
# PYTHON ENTRY POINT GUARD
# ==================================================================
# This ensures main() only runs when this file is executed directly:
#   python main.py  ✓
# It does NOT run when imported:
#   import main     ✗ (main() won't execute)
# ==================================================================
if __name__ == "__main__":
    main()