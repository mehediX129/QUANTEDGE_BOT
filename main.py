"""
main.py

Entry point for QuantEdge Trading Bot.
Run: python main.py
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
from strategies import DEFAULT_STRATEGY, STRATEGIES


def display_startup_banner():
    """Display startup banner."""
    banner = f"""
╔══════════════════════════════════════════════╗
║         QUANTEDGE TRADING BOT v1.0          ║
╠══════════════════════════════════════════════╣
║  Mode:      {TRADING_MODE:<30} ║
║  Portfolio: ${PORTFOLIO_SIZE:<29} ║
║  Symbols:   {', '.join(SYMBOLS[:2])}{'...' if len(SYMBOLS) > 2 else '':<30} ║
║  Timeframe: {PRIMARY_TIMEFRAME:<30} ║
║  Strategy:  {DEFAULT_STRATEGY:<30} ║
║  Started:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<30} ║
╚══════════════════════════════════════════════╝
    """
    print(banner)


def scan_for_signals(collector, strategy):
    """
    Scan all symbols for trading signals.
    
    Args:
        collector: DataCollector instance
        strategy: Strategy instance
    
    Returns:
        List of signal dictionaries
    """
    signals_found = []
    
    log.info("--- Scanning for Trading Signals ---")
    
    for symbol in SYMBOLS:
        log.info(f"Analyzing {symbol}...")
        
        # Fetch OHLCV data (need at least 100 candles for indicators)
        df = collector.fetch_ohlcv(symbol, timeframe=PRIMARY_TIMEFRAME, limit=200)
        
        if df is None or len(df) < 50:
            log.warning(f"  ⚠ {symbol}: Insufficient data (got {len(df) if df is not None else 0} candles)")
            continue
        
        # Generate signals using our strategy
        df = strategy.generate_signals(df)
        
        # Get the latest signal
        latest_signal = df["signal"].iloc[-1]
        latest = df.iloc[-1]
        
        # Display indicator values
        rsi = latest.get("RSI", "N/A")
        adx = latest.get("ADX", "N/A")
        ema_20 = latest.get("EMA_20", "N/A")
        ema_50 = latest.get("EMA_50", "N/A")
        vol_ratio = latest.get("Volume_Ratio", "N/A")
        close = latest["close"]
        
        # Format the indicator summary
        rsi_str = f"RSI={rsi:.1f}" if not isinstance(rsi, str) else f"RSI={rsi}"
        adx_str = f"ADX={adx:.1f}" if not isinstance(adx, str) else f"ADX={adx}"
        vol_str = f"Vol={vol_ratio:.1f}x" if not isinstance(vol_ratio, str) else f"Vol={vol_ratio}"
        
        log.info(f"  {symbol}: Close=${close:.2f} | {rsi_str} | {adx_str} | {vol_str}")
        
        # Determine signal
        if latest_signal == 1:
            log.success(f"  🔵 BUY SIGNAL for {symbol}!")
            
            # Calculate stop loss and take profit
            entry_price = close
            stop_loss = strategy.get_stop_loss(df, len(df)-1, entry_price)
            take_profit = strategy.get_take_profit(entry_price, stop_loss)
            
            risk_pct = abs(entry_price - stop_loss) / entry_price * 100
            reward_pct = abs(take_profit - entry_price) / entry_price * 100
            
            log.info(f"    Entry: ${entry_price:.2f}")
            log.info(f"    Stop Loss: ${stop_loss:.2f} ({risk_pct:.1f}% risk)")
            log.info(f"    Take Profit: ${take_profit:.2f} ({reward_pct:.1f}% reward)")
            
            signals_found.append({
                "symbol": symbol,
                "signal": "BUY",
                "entry": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "timestamp": datetime.now(),
            })
            
        elif latest_signal == -1:
            log.warning(f"  🔴 SELL SIGNAL for {symbol}!")
            signals_found.append({
                "symbol": symbol,
                "signal": "SELL",
                "entry": close,
                "timestamp": datetime.now(),
            })
        else:
            trend = "↗ UPTREND" if (isinstance(ema_20, (int, float)) and isinstance(ema_50, (int, float)) and ema_20 > ema_50) else "↘ DOWNTREND"
            log.info(f"  ⚪ HOLD - No signal ({trend})")
    
    # Summary
    buy_count = sum(1 for s in signals_found if s["signal"] == "BUY")
    sell_count = sum(1 for s in signals_found if s["signal"] == "SELL")
    log.info(f"--- Scan Complete: {buy_count} BUY, {sell_count} SELL, {len(SYMBOLS)-buy_count-sell_count} HOLD ---")
    
    return signals_found


def main():
    """Main function."""
    
    # Step 1: Banner
    display_startup_banner()
    
    # Step 2: Log startup
    log.info("=" * 50)
    log.info("QuantEdge Trading Bot - Starting Up")
    log.info(f"Trading Mode: {TRADING_MODE}")
    log.info(f"Portfolio: ${PORTFOLIO_SIZE}")
    log.info(f"Symbols: {SYMBOLS}")
    log.info(f"Timeframe: {PRIMARY_TIMEFRAME}")
    log.info(f"Strategy: {DEFAULT_STRATEGY}")
    log.info("=" * 50)
    
    # Step 3: Validate config
    if not SYMBOLS:
        log.error("No symbols configured!")
        sys.exit(1)
    
    log.success("Configuration validated!")
    
    # Step 4: Initialize DataCollector
    log.info("Connecting to exchange...")
    try:
        collector = DataCollector()
        log.success("Exchange connected!")
    except Exception as e:
        log.error(f"Exchange connection failed: {e}")
        sys.exit(1)
    
    # Step 5: Initialize Strategy
    log.info(f"Loading strategy: {DEFAULT_STRATEGY}")
    StrategyClass = STRATEGIES.get(DEFAULT_STRATEGY)
    if StrategyClass is None:
        log.error(f"Strategy '{DEFAULT_STRATEGY}' not found!")
        sys.exit(1)
    
    strategy = StrategyClass()
    log.success(f"Strategy '{strategy.name}' loaded!")
    
    # Step 6: Quick exchange health check
    if not collector.check_exchange_status():
        log.error("Exchange appears offline!")
        sys.exit(1)
    
    # Step 7: Run initial signal scan
    log.info("")
    log.info("Running initial market scan...")
    log.info("")
    signals = scan_for_signals(collector, strategy)
    
    # Step 8: Display results
    print("\n" + "=" * 60)
    print("  SIGNAL SCAN RESULTS")
    print("=" * 60)
    if signals:
        for sig in signals:
            if sig["signal"] == "BUY":
                print(f"  🔵 {sig['symbol']}: {sig['signal']}")
                print(f"     Entry: ${sig['entry']:.2f}")
                print(f"     Stop Loss: ${sig['stop_loss']:.2f}")
                print(f"     Take Profit: ${sig['take_profit']:.2f}")
            else:
                print(f"  🔴 {sig['symbol']}: {sig['signal']}")
        print("-" * 60)
        print(f"  Total Signals: {len(signals)}")
    else:
        print("  No trading signals found at this time.")
    print("=" * 60 + "\n")
    
    # Step 9: Main loop
    log.info("Signal scan complete.")
    log.info("(Automated trading loop coming in future chapters)")
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