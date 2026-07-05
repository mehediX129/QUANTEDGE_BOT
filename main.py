"""
main.py

Entry point for QuantEdge Trading Bot.
Run this file to start the bot: python main.py
"""

import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import our modules
from utils.logger import log
from config.settings import (
    TRADING_MODE,
    SYMBOLS,
    PORTFOLIO_SIZE,
    PRIMARY_TIMEFRAME,
)
from data.collector import DataCollector


def display_startup_banner():
    """Display a nice startup banner in the console."""
    banner = f"""
╔══════════════════════════════════════════════╗
║         QUANTEDGE TRADING BOT v1.0          ║
╠══════════════════════════════════════════════╣
║  Mode:      {TRADING_MODE:<30} ║
║  Portfolio: ${PORTFOLIO_SIZE:<29} ║
║  Symbols:   {', '.join(SYMBOLS[:2])}{'...' if len(SYMBOLS) > 2 else '':<30} ║
║  Timeframe: {PRIMARY_TIMEFRAME:<30} ║
║  Started:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<30} ║
╚══════════════════════════════════════════════╝
    """
    print(banner)


def test_exchange_connection(collector: DataCollector):
    """
    Test the exchange connection and display market data.
    
    This function:
    1. Checks if exchange is online
    2. Fetches current prices for all symbols
    3. Fetches recent OHLCV data
    4. Displays a summary
    """
    
    log.info("--- Exchange Connection Test ---")
    
    # Test 1: Exchange Status
    log.info("Test 1: Checking exchange status...")
    if collector.check_exchange_status():
        log.success("✓ Exchange is online!")
    else:
        log.error("✗ Exchange appears to be offline")
        return
    
    # Test 2: Current Prices
    log.info("Test 2: Fetching current prices...")
    prices = collector.get_all_prices()
    
    print("\n" + "="*50)
    print("  CURRENT MARKET PRICES")
    print("="*50)
    for symbol, price in prices.items():
        if price:
            print(f"  {symbol:<12} : ${price:>12,.2f}")
        else:
            print(f"  {symbol:<12} : ERROR FETCHING")
    print("="*50 + "\n")
    
    # Test 3: OHLCV Data
    log.info("Test 3: Fetching OHLCV data...")
    for symbol in SYMBOLS[:2]:  # Test only first 2 symbols to save time
        df = collector.fetch_ohlcv(symbol, limit=5)
        if df is not None:
            log.success(f"✓ {symbol}: Got {len(df)} candles")
            latest = df.iloc[-1]
            log.info(f"  Latest {symbol} candle: Open=${latest['open']:.2f}, "
                    f"High=${latest['high']:.2f}, Low=${latest['low']:.2f}, "
                    f"Close=${latest['close']:.2f}")
        else:
            log.error(f"✗ {symbol}: Failed to fetch OHLCV")
    
    log.info("--- Connection Test Complete ---")


def main():
    """Main function that starts the trading bot."""
    
    # Step 1: Show startup banner
    display_startup_banner()
    
    # Step 2: Log system information
    log.info("=" * 50)
    log.info("QuantEdge Trading Bot - Starting Up")
    log.info(f"Trading Mode: {TRADING_MODE}")
    log.info(f"Portfolio Size: ${PORTFOLIO_SIZE}")
    log.info(f"Symbols: {SYMBOLS}")
    log.info(f"Timeframe: {PRIMARY_TIMEFRAME}")
    log.info("=" * 50)
    
    # Step 3: Validate configuration
    log.info("Validating configuration...")
    
    if not SYMBOLS:
        log.error("No trading symbols configured!")
        sys.exit(1)
    
    if TRADING_MODE not in ["paper", "live"]:
        log.error(f"Invalid TRADING_MODE: {TRADING_MODE}")
        sys.exit(1)
    
    log.success("Configuration validated!")
    
    # Step 4: Initialize DataCollector
    log.info("Initializing exchange connection...")
    try:
        collector = DataCollector()
        log.success("Exchange connection established!")
    except Exception as e:
        log.error(f"Failed to connect to exchange: {e}")
        log.error("Please check:")
        log.error("  1. API keys in .env file are correct")
        log.error("  2. Internet connection is working")
        log.error("  3. Binance is not down")
        sys.exit(1)
    
    # Step 5: Run connection test
    test_exchange_connection(collector)
    
    # Step 6: Main loop
    log.info("Bot is ready for trading operations.")
    log.info("(Full trading logic coming in future chapters)")
    log.info("Press Ctrl+C to stop.\n")
    
    try:
        while True:
            log.debug("Bot heartbeat...")
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("")
        log.info("Shutdown signal received (Ctrl+C)")
        log.info("QuantEdge Trading Bot - Shutting Down")
        log.info("Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()