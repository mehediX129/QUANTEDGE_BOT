"""
main_backtest.py — Optimized Backtest Runner
============================================
QuantEdge Trading Bot - Backtesting Module

PURPOSE:
    Tests the Multi-Timeframe Confluence Swing Strategy on historical
    data to find optimal parameters and measure performance metrics.

WHAT THIS FILE DOES:
    1. Fetches historical OHLCV data ONCE per symbol (no repeated API calls)
    2. Tests 36 parameter combinations per symbol (4 RSI × 3 Vol × 3 ADX)
    3. Simulates trades using the BacktestEngine
    4. Calculates ALL performance metrics (Sharpe, Sortino, Calmar, MaxDD, etc.)
    5. Finds the best parameter combination based on Sharpe Ratio
    6. Displays a final summary table

WHY THIS APPROACH:
    - Single data fetch per symbol eliminates API rate limit issues
    - Runs ~10x faster than previous version (2-3 min vs 15+ min)
    - All combinations tested on identical data for fair comparison

RUN COMMAND:
    python main_backtest.py

OUTPUT:
    - Per-symbol: Best parameters with all metrics
    - Final summary table comparing all symbols

AUTHOR: QuantEdge Bot Development Team
VERSION: 2.0 (Optimized)
DATE: 2026-07-07
"""

# ============================================================================
# IMPORTS
# ============================================================================

import sys
from pathlib import Path

# --------------------------------------------------------------------------
# PATH SETUP
# --------------------------------------------------------------------------
# Add the project root folder to Python's module search path.
# __file__ = D:\Projects\quantedge_bot\main_backtest.py
# .parent  = D:\Projects\quantedge_bot\  (project root)
# Without this, Python cannot find our custom modules (utils, config, etc.)
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# --------------------------------------------------------------------------
# CUSTOM MODULE IMPORTS
# --------------------------------------------------------------------------
# Each import serves a specific purpose in the backtesting pipeline:
from utils.logger import log                    # Professional logging via loguru
from config.settings import (                    # Centralized configuration
    SYMBOLS,                                     # List of trading pairs to test
    PRIMARY_TIMEFRAME,                           # Main timeframe (default: "4h")
    PORTFOLIO_SIZE,                              # Initial capital in USDT
)
from data.collector import DataCollector         # Fetches OHLCV from exchange
from strategies.swing_strategy import SwingStrategy  # Signal generation logic
from backtesting.backtest_engine import BacktestEngine  # Trade simulation + metrics


# ============================================================================
# CORE FUNCTION: test_all_params_for_symbol()
# ============================================================================

def test_all_params_for_symbol(
    symbol: str,
    df,
    rsi_levels: list,
    vol_multipliers: list,
    adx_levels: list
) -> tuple:
    """
    Test ALL parameter combinations on PRE-FETCHED data.
    
    This function takes already-downloaded OHLCV data and runs the
    strategy with every possible parameter combination. No additional
    exchange API calls are made — this is pure CPU computation.
    
    PARAMETERS:
    -----------
    symbol : str
        Trading pair name, e.g., "BTC/USDT" (for logging only)
    
    df : pandas.DataFrame
        OHLCV data with columns: [timestamp, open, high, low, close, volume]
        This data is REUSED across all parameter combinations
    
    rsi_levels : list
        RSI buy zone thresholds to test, e.g., [30, 35, 40, 45]
        Strategy buys when RSI falls BELOW this value
    
    vol_multipliers : list
        Volume spike multipliers to test, e.g., [1.0, 1.2, 1.5]
        Strategy requires volume > (average × multiplier)
    
    adx_levels : list
        ADX trend strength thresholds to test, e.g., [15, 20, 25]
        Strategy requires ADX > this value to confirm trending market
    
    RETURNS:
    --------
    tuple: (best_params, best_result)
        best_params  : dict with the winning parameter combination
        best_result  : dict with complete performance metrics
        Returns (None, None) if no combination generated any trades
    
    HOW IT WORKS:
    -------------
    1. Loop through every combination of RSI × Volume × ADX
    2. For each combination:
       a. Create a fresh strategy instance with test parameters
       b. Generate BUY/SELL signals on a COPY of the data
       c. If signals exist, run backtest simulation
       d. Compare Sharpe Ratio to find the best
    3. Return the best-performing parameter set
    
    WHY SHARPE RATIO AS SELECTION CRITERION:
        - Sharpe measures risk-adjusted return (return per unit of risk)
        - Higher Sharpe = better returns for the same risk level
        - Industry standard for comparing strategies
        - Less prone to overfitting than pure return %
    """
    
    # ------------------------------------------------------------------
    # Initialize tracking variables
    # ------------------------------------------------------------------
    best_sharpe = -999.0      # Start very low, any valid result will beat this
    best_params = None         # Will store the winning parameter dict
    best_result = None         # Will store the complete backtest result
    tested = 0                 # Total combinations attempted
    with_trades = 0            # Combinations that actually generated trades
    
    # ------------------------------------------------------------------
    # TRIPLE NESTED LOOP: Test every parameter combination
    # ------------------------------------------------------------------
    # 4 RSI levels × 3 Volume multipliers × 3 ADX levels = 36 combinations
    # Example iterations:
    #   RSI=30, Vol=1.0, ADX=15
    #   RSI=30, Vol=1.0, ADX=20
    #   ...and so on...
    # ------------------------------------------------------------------
    for rsi_buy in rsi_levels:
        for vol_mult in vol_multipliers:
            for adx_min in adx_levels:
                tested += 1

                # Check which strategy this asset uses
                from strategies import ASSET_STRATEGY_MAP
                asset_strategy = ASSET_STRATEGY_MAP.get(symbol, "swing_combo")
                
                # BTC: Skip parameter sweep, use fixed Donchian params (1 test only)
                if asset_strategy == "btc_breakout" and tested > 1:
                    continue
                
                # ----------------------------------------------------------
                # Build parameter dictionary for this combination
                # ----------------------------------------------------------
                # These parameters OVERRIDE the strategy's default values
                # from config/settings.py. This is how we test "what if"
                # scenarios without changing the actual config.
                # ----------------------------------------------------------
                
                # Check for asset-specific overrides from config
                from config.settings import ASSET_STRATEGY_CONFIG
                asset_cfg = ASSET_STRATEGY_CONFIG.get(symbol, {})
                
                # BTC: Use Donchian breakout parameters
                if asset_strategy == "btc_breakout":
                    params = {
                        "donchian_period": asset_cfg.get("donchian_period", 20),
                        "atr_period": 14,
                        "atr_stop_multiplier": asset_cfg.get("atr_stop_multiplier", 3.0),
                        "adx_threshold": asset_cfg.get("adx_threshold", 20),
                        "volume_multiplier": asset_cfg.get("volume_multiplier", 1.0),
                        "risk_reward_ratio": 2.0,
                    }
                else:
                    # ETH/SOL/ADA: Use Swing strategy parameters
                    params = {
                        "ema_fast": 20,
                        "ema_slow": 50,
                        "rsi_period": 14,
                        "rsi_buy_zone": asset_cfg.get("rsi_buy_zone", rsi_buy),
                        "rsi_sell_zone": 70,
                        "volume_multiplier": asset_cfg.get("volume_multiplier", vol_mult),
                        "adx_min": asset_cfg.get("adx_threshold", adx_min),
                        "risk_reward_ratio": 2.5,
                        "atr_multiplier": 2.0,
                    }
                
                # ----------------------------------------------------------
                # Create strategy with test parameters
                # ----------------------------------------------------------
                # We create a NEW strategy instance for each combination
                # to avoid state leakage between tests.
                # ----------------------------------------------------------
                # Per-asset strategy selection
                from strategies import ASSET_STRATEGY_MAP, STRATEGIES
                strategy_name = ASSET_STRATEGY_MAP.get(symbol, "swing_combo")
                 # Use asset-specific strategy class
                StrategyClass = STRATEGIES.get(asset_strategy, SwingStrategy)
                strategy = StrategyClass()
                strategy.params = params
                
                # ----------------------------------------------------------
                # Generate signals on a COPY of the data
                # ----------------------------------------------------------
                # df.copy() is CRITICAL — without it, the strategy's
                # add_all_indicators() would modify the original DataFrame,
                # and subsequent combinations would get corrupted data.
                # ----------------------------------------------------------
                df_signals = strategy.generate_signals(df.copy())
                
                # ----------------------------------------------------------
                # Check if any BUY signals were generated
                # ----------------------------------------------------------
                # value_counts() returns a dict like {0: 195, 1: 3, -1: 2}
                # We only care about key '1' (BUY signals)
                # ----------------------------------------------------------
                signal_counts = df_signals["signal"].value_counts().to_dict()
                
                if signal_counts.get(1, 0) == 0:
                    # No BUY signals → skip backtest for this combination
                    continue
                
                # ----------------------------------------------------------
                # Run backtest simulation
                # ----------------------------------------------------------
                # BacktestEngine simulates trades with:
                # - Initial capital from settings
                # - 0.1% commission (standard Binance spot fee)
                # - 0.05% slippage (conservative estimate)
                # ----------------------------------------------------------
                engine = BacktestEngine(
                    initial_capital=PORTFOLIO_SIZE,
                    commission=0.001,     # 0.1% per trade
                    slippage=0.0005,      # 0.05% per trade
                )
                
                result = engine.run(df_signals, symbol)
                
                # ----------------------------------------------------------
                # Evaluate result
                # ----------------------------------------------------------
                # We only consider results that actually generated trades.
                # Results with 0 trades (all HOLD) are skipped.
                # ----------------------------------------------------------
                if result and result["trade_statistics"]["total_trades"] >= 3:
                    with_trades += 1
                    sharpe = result["risk_metrics"]["sharpe_ratio"]
                    
                    # ------------------------------------------------------
                    # Update best if this Sharpe is higher
                    # ------------------------------------------------------
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_result = result
                        best_params = params
    
    # ------------------------------------------------------------------
    # Log results for this symbol
    # ------------------------------------------------------------------
    log.info(f"  Tested {tested} combinations, {with_trades} generated trades")
    
    if best_params:
        # Extract key metrics for concise logging
        t = best_result["trade_statistics"]
        r = best_result["returns"]
        rm = best_result["risk_metrics"]
        
        log.success(
            f"  BEST: RSI<{best_params['rsi_buy_zone']} "
            f"Vol>{best_params['volume_multiplier']}x "
            f"ADX>{best_params['adx_min']} | "
            f"Trades:{t['total_trades']} "
            f"Win:{t['win_rate']:.0f}% "
            f"Return:{r['total_return_pct']:.1f}% "
            f"MaxDD:{rm['max_drawdown_pct']:.1f}% "
            f"Sharpe:{rm['sharpe_ratio']:.2f} "
            f"Sortino:{rm['sortino_ratio']:.2f}"
        )
    else:
        log.warning(f"  No profitable parameter combination found for {symbol}")
    
    return best_params, best_result


# ============================================================================
# MAIN FUNCTION: main()
# ============================================================================

def main():
    """
    Main entry point for the backtest runner.
    
    EXECUTION FLOW:
    1. Display header
    2. Define parameter grid to test
    3. Initialize DataCollector (ONE TIME only)
    4. For each symbol in SYMBOLS:
       a. Fetch OHLCV data ONCE
       b. Test all 36 parameter combinations
       c. Record best parameters and metrics
    5. Display final summary table
    
    WHY THIS ORDER:
    - Fetching data once per symbol eliminates redundant API calls
    - Testing all combinations on the same data ensures fair comparison
    - Final summary allows quick visual comparison across symbols
    """
    
    # ------------------------------------------------------------------
    # Step 1: Display header
    # ------------------------------------------------------------------
    log.info("=" * 60)
    log.info("QUANTEDGE BACKTEST ENGINE v2.0")
    log.info("=" * 60)
    log.info(f"Symbols: {SYMBOLS}")
    log.info(f"Timeframe: {PRIMARY_TIMEFRAME}")
    log.info(f"Initial Capital: ${PORTFOLIO_SIZE:,.0f}")
    log.info(f"Parameter Grid: RSI×Vol×ADX = 4×3×3 = 36 combinations/symbol")
    log.info("=" * 60)
    
    # ------------------------------------------------------------------
    # Step 2: Define parameter grid
    # ------------------------------------------------------------------
    # RSI Buy Zone thresholds to test:
    #   30 = Very oversold only (conservative, fewer trades)
    #   35 = Oversold
    #   40 = Near oversold (balanced)
    #   45 = Slightly below neutral (aggressive, more trades)
    rsi_levels = [30, 35, 40, 45]
    
    # Volume multiplier thresholds:
    #   1.0 = Any volume above average
    #   1.2 = 20% above average
    #   1.5 = 50% above average (strong volume confirmation)
    vol_multipliers = [1.0, 1.2, 1.5]
    
    # ADX trend strength thresholds:
    #   15 = Weak trend acceptable
    #   20 = Moderate trend (standard)
    #   25 = Strong trend only (conservative)
    adx_levels = [15, 20, 25]
    
    # ------------------------------------------------------------------
    # Step 3: Initialize DataCollector (ONE TIME)
    # ------------------------------------------------------------------
    # DataCollector connects to Binance Testnet.
    # We initialize once and reuse for all symbols.
    # This saves ~3-5 seconds per symbol × 4 symbols = ~15 seconds
    # ------------------------------------------------------------------
    log.info("Connecting to exchange for data fetch...")
    collector = DataCollector()
    log.info("Exchange connection established.\n")
    
    # ------------------------------------------------------------------
    # Step 4: Test each symbol
    # ------------------------------------------------------------------
    all_best = {}  # Will store: {symbol: {"params": {...}, "result": {...}}}
    
    for symbol in SYMBOLS:
        log.info(f"{'='*60}")
        log.info(f"BACKTESTING: {symbol}")
        log.info(f"{'='*60}")
        
        # --------------------------------------------------------------
        # Fetch historical data (ONE API call per symbol)
        # --------------------------------------------------------------
        # 200 candles × 4 hours = 800 hours ≈ 33 days of data
        # This is the maximum available on Binance Testnet for 4h candles.
        # For production backtesting, increase limit to 1000+ for better
        # statistical significance.
        # --------------------------------------------------------------
        # Per-asset timeframe (research-backed)
        from config.settings import ASSET_TIMEFRAMES
        asset_timeframe = ASSET_TIMEFRAMES.get(symbol, PRIMARY_TIMEFRAME)
        df = collector.fetch_ohlcv(
            symbol,
            timeframe=asset_timeframe,
            limit=200
        )
        
        # Validate data
        if df is None or len(df) < 100:
            log.warning(
                f"⚠ {symbol}: Insufficient data "
                f"({len(df) if df is not None else 0} candles). Skipping."
            )
            continue
        
        log.info(f"Data: {len(df)} candles | "
                f"Period: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
        
        # --------------------------------------------------------------
        # Test all parameter combinations
        # --------------------------------------------------------------
        best_params, best_result = test_all_params_for_symbol(
            symbol, df, rsi_levels, vol_multipliers, adx_levels
        )
        
        # --------------------------------------------------------------
        # Store best result for this symbol
        # --------------------------------------------------------------
        if best_params:
            all_best[symbol] = {
                "params": best_params,
                "result": best_result,
            }
        else:
            log.warning(f"  No valid parameters found for {symbol}")
    
    # ------------------------------------------------------------------
    # Step 5: Display final summary
    # ------------------------------------------------------------------
    log.info("")
    log.info("=" * 85)
    log.info("FINAL SUMMARY — BEST PARAMETERS BY SYMBOL")
    log.info("=" * 85)
    
    # Table header
    header = (
        f"{'Symbol':<12} "
        f"{'RSI<':>5} "
        f"{'Vol>':>5} "
        f"{'ADX>':>5} "
        f"{'Trades':>7} "
        f"{'Win%':>7} "
        f"{'Ret%':>7} "
        f"{'MaxDD%':>7} "
        f"{'Sharpe':>7} "
        f"{'Sortino':>7}"
    )
    log.info(header)
    log.info("-" * 85)
    
    # Table rows
    for symbol, data in all_best.items():
        p = data["params"]
        t = data["result"]["trade_statistics"]
        r = data["result"]["returns"]
        rm = data["result"]["risk_metrics"]
        
        row = (
            f"{symbol:<12} "
            f"{p['rsi_buy_zone']:>5} "
            f"{p['volume_multiplier']:>4.1f} "
            f"{p['adx_min']:>5} "
            f"{t['total_trades']:>7} "
            f"{t['win_rate']:>6.1f}% "
            f"{r['total_return_pct']:>6.2f}% "
            f"{rm['max_drawdown_pct']:>6.2f}% "
            f"{rm['sharpe_ratio']:>7.2f} "
            f"{rm['sortino_ratio']:>7.2f}"
        )
        log.info(row)
    
    log.info("=" * 85)
    
    # ------------------------------------------------------------------
    # Step 6: Interpretation guide
    # ------------------------------------------------------------------
    log.info("")
    log.info("📊 METRICS INTERPRETATION GUIDE:")
    log.info("  Sharpe > 1.0  = Good risk-adjusted returns")
    log.info("  Sortino > 2.0 = Good returns with low downside risk")
    log.info("  MaxDD < 10%   = Acceptable drawdown for swing trading")
    log.info("  Win Rate       = Lower is OK if Avg Win >> Avg Loss (high RR)")
    log.info("  Profit Factor  = > 1.5 is good, > 2.0 is excellent")
    log.info("")
    log.info("⚠ NOTE: Only 33 days of testnet data tested.")
    log.info("   For production, backtest on 6-12 months of real exchange data.")
    log.info("")


# ============================================================================
# PYTHON ENTRY POINT GUARD
# ============================================================================
# __name__ == "__main__" is True ONLY when this file is executed directly:
#   python main_backtest.py  ✓
# It is False when this file is imported by another script:
#   from main_backtest import test_all_params_for_symbol  ✗ (won't run main())
# ============================================================================
if __name__ == "__main__":
    main()