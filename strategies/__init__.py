from strategies.swing_strategy import SwingStrategy
from strategies.donchian_breakout import DonchianBreakoutStrategy

STRATEGIES = {
    "swing_combo": SwingStrategy,
    "donchian_breakout": DonchianBreakoutStrategy,
}

DEFAULT_STRATEGY = "swing_combo"

SYMBOL_STRATEGY_MAP = {
    "BTC/USDT": "donchian_breakout",
    "ETH/USDT": "swing_combo",
    "SOL/USDT": "swing_combo",
    "ADA/USDT": "swing_combo",
}