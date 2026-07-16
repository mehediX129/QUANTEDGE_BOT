"""
backtesting/walk_forward.py

Walk-Forward Validation Framework.

WHY WALK-FORWARD:
Regular backtesting finds the best parameters for ALL data (in-sample).
This causes OVERFITTING — parameters that work perfectly on past data
but fail on future data.

Walk-forward fixes this by:
1. Splitting data into training (older 70%) and testing (newer 30%)
2. Finding best parameters ONLY on training data
3. Testing those parameters on COMPLETELY UNSEEN test data
4. The test result is the REAL expected performance

This is the industry standard for strategy validation.
Used by professional quant funds worldwide.
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from utils.logger import log
from config.settings import PORTFOLIO_SIZE, PRIMARY_TIMEFRAME
from data.collector import DataCollector
from strategies.swing_strategy import SwingStrategy
from backtesting.backtest_engine import BacktestEngine


def walk_forward_analysis(
    symbol: str,
    train_ratio: float = 0.70,
    limit: int = 200,
    min_trades: int = 5
) -> Dict:
    """
    Perform walk-forward validation on a symbol.
    
    Args:
        symbol: Trading pair
        train_ratio: Fraction of data for training (default 70%)
        limit: Total candles to fetch
        min_trades: Minimum trades required for valid result
    
    Returns:
        Dictionary with train/test metrics
    """
    log.info(f"\n{'='*60}")
    log.info(f"WALK-FORWARD VALIDATION: {symbol}")
    log.info(f"{'='*60}")
    
    # Step 1: Fetch data
    collector = DataCollector()
    from config.settings import BACKTEST_CANDLE_LIMIT
    df = collector.fetch_ohlcv(symbol, timeframe=PRIMARY_TIMEFRAME, limit=BACKTEST_CANDLE_LIMIT)
    
    if df is None or len(df) < 100:
        log.error(f"Insufficient data for {symbol}")
        return None
    
    # Step 2: Split into train/test
    split_idx = int(len(df) * train_ratio)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()
    
    log.info(f"Data: {len(df)} total | Train: {len(train_df)} | Test: {len(test_df)}")
    log.info(f"Train period: {train_df['timestamp'].iloc[0]} to {train_df['timestamp'].iloc[-1]}")
    log.info(f"Test period:  {test_df['timestamp'].iloc[0]} to {test_df['timestamp'].iloc[-1]}")
    
    # Step 3: Find best parameters on TRAINING data only
    best_params, train_result = _find_best_params(train_df, symbol, min_trades)
    
    if best_params is None:
        log.warning(f"No valid parameters found in training data")
        return None
    
    # Step 4: Test on UNSEEN test data
    log.info(f"\nTesting best params on OUT-OF-SAMPLE data...")
    
    strategy = SwingStrategy()
    strategy.params = best_params
    test_signals = strategy.generate_signals(test_df.copy())
    
    engine = BacktestEngine(
        initial_capital=PORTFOLIO_SIZE,
        commission=0.001,
        slippage=0.0005,
    )
    test_result = engine.run(test_signals, f"{symbol}_TEST")
    
    # Step 5: Compare train vs test
    if test_result and test_result["trade_statistics"]["total_trades"] > 0:
        train_sharpe = train_result["risk_metrics"]["sharpe_ratio"]
        test_sharpe = test_result["risk_metrics"]["sharpe_ratio"]
        train_return = train_result["returns"]["total_return_pct"]
        test_return = test_result["returns"]["total_return_pct"]
        
        # Degradation check
        sharpe_degradation = ((train_sharpe - test_sharpe) / train_sharpe * 100) if train_sharpe != 0 else 0
        return_degradation = ((train_return - test_return) / train_return * 100) if train_return != 0 else 0
        
        log.info(f"\n{'='*60}")
        log.info(f"WALK-FORWARD RESULTS: {symbol}")
        log.info(f"{'='*60}")
        log.info(f"{'Metric':<20} {'Train':>10} {'Test':>10} {'Change':>10}")
        log.info(f"{'-'*50}")
        log.info(f"{'Return %':<20} {train_return:>10.2f} {test_return:>10.2f} {return_degradation:>9.1f}%")
        log.info(f"{'Sharpe':<20} {train_sharpe:>10.2f} {test_sharpe:>10.2f} {sharpe_degradation:>9.1f}%")
        log.info(f"{'Trades':<20} {train_result['trade_statistics']['total_trades']:>10} {test_result['trade_statistics']['total_trades']:>10}")
        log.info(f"{'Win Rate':<20} {train_result['trade_statistics']['win_rate']:>9.1f}% {test_result['trade_statistics']['win_rate']:>9.1f}%")
        log.info(f"{'='*60}")
        
        # Quality assessment
        if sharpe_degradation < 20 and test_sharpe > 0.5:
            log.success(f"✅ Strategy is ROBUST — test performance close to train")
        elif sharpe_degradation < 50:
            log.warning(f"⚠ Strategy shows MODERATE degradation — needs monitoring")
        else:
            log.error(f"❌ Strategy OVERFITTED — test performance much worse than train")
        
        return {
            "symbol": symbol,
            "best_params": best_params,
            "train_result": train_result,
            "test_result": test_result,
            "sharpe_degradation": sharpe_degradation,
            "return_degradation": return_degradation,
            "is_robust": sharpe_degradation < 20 and test_sharpe > 0.5,
        }
    
    log.warning(f"No trades in test period — insufficient data for validation")
    return None


def _find_best_params(df, symbol, min_trades=5):
    """Find best parameters on given data (internal function)."""
    rsi_levels = [30, 35, 40, 45]
    vol_multipliers = [1.0, 1.2, 1.5]
    adx_levels = [15, 20, 25]
    
    best_sharpe = -999
    best_params = None
    best_result = None
    
    for rsi_buy in rsi_levels:
        for vol_mult in vol_multipliers:
            for adx_min in adx_levels:
                
                # Check for asset-specific overrides from config
                from config.settings import ASSET_STRATEGY_CONFIG
                asset_cfg = ASSET_STRATEGY_CONFIG.get(symbol, {})
                
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
                
                strategy = SwingStrategy()
                strategy.params = params
                df_signals = strategy.generate_signals(df.copy())
                
                signal_counts = df_signals["signal"].value_counts().to_dict()
                if signal_counts.get(1, 0) < 1:
                    continue
                
                engine = BacktestEngine(PORTFOLIO_SIZE, 0.001, 0.0005)
                result = engine.run(df_signals, symbol)
                
                if result and result["trade_statistics"]["total_trades"] >= min_trades:
                    sharpe = result["risk_metrics"]["sharpe_ratio"]
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_result = result
                        best_params = params
    
    return best_params, best_result


def run_walk_forward_all(symbols: list, limit: int = 200):
    """Run walk-forward on all symbols."""
    results = {}
    
    for symbol in symbols:
        result = walk_forward_analysis(symbol, limit=limit)
        if result:
            results[symbol] = result
    
    # Final verdict
    log.info(f"\n{'='*70}")
    log.info("FINAL WALK-FORWARD VERDICT")
    log.info(f"{'='*70}")
    
    robust_count = sum(1 for r in results.values() if r.get("is_robust"))
    
    for symbol, r in results.items():
        verdict = "✅ ROBUST" if r.get("is_robust") else "⚠ OVERFITTED"
        log.info(f"{symbol:<12} | Sharpe: {r['train_result']['risk_metrics']['sharpe_ratio']:.2f} → "
                f"{r['test_result']['risk_metrics']['sharpe_ratio']:.2f} | "
                f"Degradation: {r['sharpe_degradation']:.0f}% | {verdict}")
    
    log.info(f"\n{robust_count}/{len(symbols)} symbols show robust performance")
    
    return results


if __name__ == "__main__":
    from config.settings import SYMBOLS
    results = run_walk_forward_all(SYMBOLS)


from itertools import combinations
from strategies.donchian_breakout import DonchianBreakoutStrategy


def _find_best_donchian_params(df, symbol, min_trades=5):
    """Sweep lookback-period combinations for the Donchian ensemble."""
    candidate_periods = [5, 10, 15, 20, 30, 55, 80]

    candidate_ensembles = (
        [[p] for p in candidate_periods]
        + list(combinations(candidate_periods, 2))
        + list(combinations(candidate_periods, 3))
    )

    best_sharpe = -999
    best_params = None
    best_result = None

    for ensemble in candidate_ensembles:
        strategy = DonchianBreakoutStrategy(lookback_periods=list(ensemble))
        df_signals = strategy.generate_signals(df.copy())

        signal_counts = df_signals["signal"].value_counts().to_dict()
        if signal_counts.get(1, 0) < 1:
            continue

        engine = BacktestEngine(PORTFOLIO_SIZE, 0.001, 0.0005)
        result = engine.run(df_signals, symbol)

        if result and result["trade_statistics"]["total_trades"] >= min_trades:
            sharpe = result["risk_metrics"]["sharpe_ratio"]
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_result = result
                best_params = {"lookback_periods": list(ensemble)}

    return best_params, best_result