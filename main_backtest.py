"""
main_backtest.py

Backtest runner with parameter optimization.
Tests multiple strategy parameter combinations and finds the best.

Run: python main_backtest.py
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import log
from config.settings import SYMBOLS, PRIMARY_TIMEFRAME, PORTFOLIO_SIZE
from data.collector import DataCollector
from strategies.swing_strategy import SwingStrategy
from backtesting.backtest_engine import BacktestEngine


def run_backtest_with_params(symbol, strategy_params, limit=200):
    """
    Run backtest with custom strategy parameters.
    """
    collector = DataCollector()
    df = collector.fetch_ohlcv(symbol, timeframe=PRIMARY_TIMEFRAME, limit=limit)
    
    if df is None or len(df) < 100:
        return None
    
    # Create strategy with custom params
    strategy = SwingStrategy()
    strategy.params = strategy_params  # Override params
    
    df = strategy.generate_signals(df)
    
    signal_counts = df["signal"].value_counts().to_dict()
    total_signals = signal_counts.get(1, 0) + signal_counts.get(-1, 0)
    
    if total_signals == 0:
        return None  # Skip if no signals
    
    engine = BacktestEngine(
        initial_capital=PORTFOLIO_SIZE,
        commission=0.001,
        slippage=0.0005,
    )
    
    results = engine.run(df, symbol)
    return results


def parameter_sweep(symbol):
    """
    Test multiple parameter combinations.
    
    Varying:
    - RSI buy zone: 30 to 50
    - Volume multiplier: 1.0 to 2.0
    - ADX threshold: 15 to 30
    """
    log.info(f"\n{'='*60}")
    log.info(f"PARAMETER SWEEP: {symbol}")
    log.info(f"{'='*60}")
    
    best_result = None
    best_params = None
    best_sharpe = -999
    
    # Parameter grid
    rsi_levels = [30, 35, 40, 45]
    vol_multipliers = [1.0, 1.2, 1.5]
    adx_levels = [15, 20, 25]
    
    tested = 0
    with_signals = 0
    
    for rsi_buy in rsi_levels:
        for vol_mult in vol_multipliers:
            for adx_min in adx_levels:
                tested += 1
                
                params = {
                    "ema_fast": 20,
                    "ema_slow": 50,
                    "rsi_period": 14,
                    "rsi_buy_zone": rsi_buy,
                    "rsi_sell_zone": 70,
                    "volume_multiplier": vol_mult,
                    "adx_min": adx_min,
                    "risk_reward_ratio": 2.5,
                }
                
                result = run_backtest_with_params(symbol, params, limit=200)
                
                if result and result["trade_statistics"]["total_trades"] > 0:
                    with_signals += 1
                    sharpe = result["risk_metrics"]["sharpe_ratio"]
                    trades = result["trade_statistics"]["total_trades"]
                    win_rate = result["trade_statistics"]["win_rate"]
                    return_pct = result["returns"]["total_return_pct"]
                    max_dd = result["risk_metrics"]["max_drawdown_pct"]
                    
                    log.info(
                        f"RSI<{rsi_buy} Vol>{vol_mult}x ADX>{adx_min} | "
                        f"Trades:{trades} Win:{win_rate:.0f}% "
                        f"Ret:{return_pct:.1f}% DD:{max_dd:.1f}% Sharpe:{sharpe:.2f}"
                    )
                    
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_result = result
                        best_params = params
    
    log.info(f"\nTested {tested} combinations, {with_signals} generated trades")
    
    if best_params:
        log.success(f"\nBEST PARAMS for {symbol}:")
        log.success(f"  RSI Buy Zone: < {best_params['rsi_buy_zone']}")
        log.success(f"  Volume Multiplier: > {best_params['volume_multiplier']}x")
        log.success(f"  ADX Threshold: > {best_params['adx_min']}")
        log.success(f"  Sharpe: {best_sharpe:.2f}")
        
        t = best_result["trade_statistics"]
        r = best_result["returns"]
        rm = best_result["risk_metrics"]
        
        log.info(f"  Trades: {t['total_trades']} | Win Rate: {t['win_rate']}%")
        log.info(f"  Return: {r['total_return_pct']:.2f}% | Max DD: {rm['max_drawdown_pct']:.2f}%")
        log.info(f"  Profit Factor: {t['profit_factor']:.2f}")
    
    return best_params, best_result


def main():
    log.info("QUANTEDGE BACKTEST ENGINE - PARAMETER OPTIMIZATION")
    log.info(f"Testing {len(SYMBOLS)} symbols...")
    
    all_best = {}
    
    for symbol in SYMBOLS:
        best_params, best_result = parameter_sweep(symbol)
        if best_params:
            all_best[symbol] = {
                "params": best_params,
                "result": best_result,
            }
    
    # Final Summary Table
    log.info(f"\n{'='*70}")
    log.info("FINAL SUMMARY - BEST PARAMS PER SYMBOL")
    log.info(f"{'='*70}")
    log.info(f"{'Symbol':<12} {'RSI<':>5} {'Vol>':>5} {'ADX>':>5} {'Trades':>7} {'Win%':>6} {'Ret%':>7} {'MaxDD%':>7} {'Sharpe':>7}")
    log.info("-" * 70)
    
    for symbol, data in all_best.items():
        p = data["params"]
        t = data["result"]["trade_statistics"]
        r = data["result"]["returns"]
        rm = data["result"]["risk_metrics"]
        
        log.info(
            f"{symbol:<12} "
            f"{p['rsi_buy_zone']:>5} "
            f"{p['volume_multiplier']:>4.1f} "
            f"{p['adx_min']:>5} "
            f"{t['total_trades']:>7} "
            f"{t['win_rate']:>5.1f}% "
            f"{r['total_return_pct']:>6.2f}% "
            f"{rm['max_drawdown_pct']:>6.2f}% "
            f"{rm['sharpe_ratio']:>7.2f}"
        )


if __name__ == "__main__":
    main()