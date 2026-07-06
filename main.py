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
from config.settings import (             # Central configuration
    TRADING_MODE,                         # "paper" or "live"
    SYMBOLS,                              # List of trading pairs
    PORTFOLIO_SIZE,                       # Total capital in USDT
    PRIMARY_TIMEFRAME,                    # Main chart timeframe (4h)
)
from data.collector import DataCollector  # Exchange connection & data fetching
from strategies import DEFAULT_STRATEGY, STRATEGIES  # Strategy registry
from risk.risk_manager import RiskManager # Risk management & position sizing


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

def scan_for_signals(collector, strategy, risk_manager):
    """
    Scan ALL configured symbols for trading signals.
    
    This is the CORE function that:
    1. Fetches 200 candles of OHLCV data per symbol
    2. Calculates all technical indicators
    3. Runs the strategy's signal generation logic
    4. For BUY signals: calculates stop loss, take profit, position size
    5. Displays compact one-line status per symbol
    
    Parameters:
        collector: DataCollector instance (fetches market data)
        strategy: Strategy instance (generates buy/sell signals)
        risk_manager: RiskManager instance (calculates position size)
    
    Returns:
        List of signal dictionaries, each containing:
        - symbol, signal (BUY/SELL), entry, stop_loss, take_profit, qty
    """
    
    signals_found = []  # Will hold all signals found in this scan
    
    # Print scan header with current time
    log.info("=" * 50)
    log.info(f"SIGNAL SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 50)
    
    # ------------------------------------------------------------------
    # Loop through each symbol (BTC, ETH, SOL, ADA)
    # ------------------------------------------------------------------
    for symbol in SYMBOLS:
        
        # --------------------------------------------------------------
        # Step 1: Fetch OHLCV candlestick data
        # --------------------------------------------------------------
        # We fetch 200 candles of 4h timeframe.
        # 200 × 4h = 800 hours = ~33 days of data.
        # This is enough for all our indicators to calculate properly.
        df = collector.fetch_ohlcv(
            symbol,
            timeframe=PRIMARY_TIMEFRAME,
            limit=200
        )
        
        # If data fetch failed or too few candles, skip this symbol
        if df is None or len(df) < 50:
            log.warning(f"⚠ {symbol}: Insufficient data (need 50+ candles)")
            continue
        
        # --------------------------------------------------------------
        # Step 2: Generate signals using our strategy
        # --------------------------------------------------------------
        # This calculates all indicators (EMA, RSI, MACD, ATR, ADX, etc.)
        # and applies the buy/sell conditions.
        # Adds a 'signal' column: 1=BUY, -1=SELL, 0=HOLD
        df = strategy.generate_signals(df)
        
        # Get the LAST row (most recent candle)
        latest_signal = df["signal"].iloc[-1]  # 1, -1, or 0
        latest = df.iloc[-1]                    # All indicator values
        
        # --------------------------------------------------------------
        # Step 3: Extract indicator values for display
        # --------------------------------------------------------------
        close = latest["close"]                  # Current price
        rsi = latest.get("RSI", None)            # RSI value (0-100)
        adx = latest.get("ADX", None)            # ADX value (trend strength)
        vol = latest.get("Volume_Ratio", None)   # Volume vs 20-period average
        
        # Format for display — handle None/Nan values gracefully
        rsi_str = f"RSI={rsi:.1f}" if rsi is not None and not (isinstance(rsi, float) and str(rsi) == 'nan') else "RSI=N/A"
        adx_str = f"ADX={adx:.1f}" if adx is not None and not (isinstance(adx, float) and str(adx) == 'nan') else "ADX=N/A"
        vol_str = f"Vol={vol:.1f}x" if vol is not None and not (isinstance(vol, float) and str(vol) == 'nan') else "Vol=N/A"
        
        # --------------------------------------------------------------
        # Step 4: BUY SIGNAL
        # --------------------------------------------------------------
        if latest_signal == 1:
            # 🔵 Bullish — all buy conditions met
            log.success(
                f"🔵 BUY  {symbol:<12} ${close:>10,.2f} | "
                f"{rsi_str} | {adx_str} | {vol_str}"
            )
            
            # Calculate stop loss using ATR (from strategy)
            entry_price = close
            stop_loss = strategy.get_stop_loss(df, len(df) - 1, entry_price)
            
            # Calculate take profit using Risk:Reward ratio
            take_profit = strategy.get_take_profit(entry_price, stop_loss)
            
            # Calculate position size using Risk Manager
            # This applies the 2% risk rule
            qty = risk_manager.calculate_position_size(
                entry_price, stop_loss, PORTFOLIO_SIZE
            )
            
            # Display trade details
            log.info(
                f"     Entry=${entry_price:,.2f} | "
                f"SL=${stop_loss:,.2f} | "
                f"TP=${take_profit:,.2f} | "
                f"Size={qty:.6f} units"
            )
            
            # Save this signal
            signals_found.append({
                "symbol": symbol,
                "signal": "BUY",
                "entry": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "qty": qty,
                "timestamp": datetime.now(),
            })
        
        # --------------------------------------------------------------
        # Step 5: SELL SIGNAL
        # --------------------------------------------------------------
        elif latest_signal == -1:
            # 🔴 Bearish — exit condition triggered
            log.warning(
                f"🔴 SELL {symbol:<12} ${close:>10,.2f} | "
                f"{rsi_str} | {adx_str} | {vol_str}"
            )
            signals_found.append({
                "symbol": symbol,
                "signal": "SELL",
                "entry": close,
                "timestamp": datetime.now(),
            })
        
        # --------------------------------------------------------------
        # Step 6: HOLD (No Signal)
        # --------------------------------------------------------------
        else:
            # ⚪ No signal — determine trend direction for context
            ema_20 = latest.get("EMA_20", None)
            ema_50 = latest.get("EMA_50", None)
            
            if ema_20 is not None and ema_50 is not None:
                trend = "↗" if ema_20 > ema_50 else "↘"
            else:
                trend = "?"
            
            log.info(
                f"⚪ HOLD {symbol:<12} ${close:>10,.2f} | "
                f"{rsi_str} | {adx_str} | {vol_str} | {trend}"
            )
    
    # ------------------------------------------------------------------
    # Print scan summary
    # ------------------------------------------------------------------
    buy_count = sum(1 for s in signals_found if s["signal"] == "BUY")
    sell_count = sum(1 for s in signals_found if s["signal"] == "SELL")
    hold_count = len(SYMBOLS) - buy_count - sell_count
    
    log.info(f"SUMMARY: {buy_count} Buy | {sell_count} Sell | {hold_count} Hold")
    log.info("=" * 50)
    
    return signals_found


# ==================================================================
# FUNCTION 3: main()
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
    
    strategy = StrategyClass()
    log.success(f"Strategy '{strategy.name}' loaded")
    
    # ------------------------------------------------------------------
    # STEP 7: Initialize Risk Manager
    # ------------------------------------------------------------------
    risk_manager = RiskManager()
    log.success("Risk Manager initialized")
    
    # ------------------------------------------------------------------
    # STEP 8: All systems go — run first scan
    # ------------------------------------------------------------------
    log.info("")
    log.info("🚀 All systems initialized. Running first market scan...")
    log.info("")
    
    scan_for_signals(collector, strategy, risk_manager)
    
    # ------------------------------------------------------------------
    # STEP 9: Continuous scanning loop
    # ------------------------------------------------------------------
    SCAN_INTERVAL_MINUTES = 15  # Scan every 15 minutes
    
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
            scan_for_signals(collector, strategy, risk_manager)
            print()  # Blank line between scans for readability
    
    # ------------------------------------------------------------------
    # STEP 10: Graceful shutdown
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