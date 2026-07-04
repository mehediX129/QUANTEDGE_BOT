"""
main.py

Entry point for QuantEdge Trading Bot.
Run this file to start the bot: python main.py
"""

import sys
from datetime import datetime
from pathlib import Path

# Add the project root to Python path (in case it's not already there)
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


def display_startup_banner():
    """
    Display a nice startup banner in the console.
    This is just for visual appeal and information.
    """
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


def main():
    """
    Main function that starts the trading bot.
    This is the entry point of the entire application.
    """
    
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
        log.error("No trading symbols configured! Please add symbols in config/settings.py")
        sys.exit(1)
    
    if TRADING_MODE not in ["paper", "live"]:
        log.error(f"Invalid TRADING_MODE: {TRADING_MODE}. Must be 'paper' or 'live'")
        sys.exit(1)
    
    log.success("Configuration validated successfully!")
    
    # Step 4: Ready for trading
    log.info("Bot is ready to start trading.")
    log.info("(Trading engine will be implemented in future chapters)")
    log.info("-" * 50)
    
    # Step 5: Placeholder for future trading loop
    # We will add the actual trading logic in later chapters
    log.info("Press Ctrl+C to stop the bot.")
    
    try:
        # This is where the main trading loop will go
        # For now, we just keep the program running
        while True:
            # We'll implement actual trading in Chapter 3
            log.debug("Bot is alive and waiting...")
            import time
            time.sleep(60)  # Wait 60 seconds
    except KeyboardInterrupt:
        log.info("")
        log.info("Shutdown signal received (Ctrl+C)")
        log.info("QuantEdge Trading Bot - Shutting Down")
        log.info("Goodbye!")
        sys.exit(0)


# ------------------------------------------------------------------
# Python special variable __name__
# ------------------------------------------------------------------
# When you run: python main.py
# Python sets __name__ = "__main__" for this file
# But if you import this file from another file, __name__ = "main"
# 
# This if-statement ensures main() only runs when this file
# is executed directly, not when imported.
if __name__ == "__main__":
    main()