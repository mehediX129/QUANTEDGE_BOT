"""
config/settings.py

Central configuration for QuantEdge Trading Bot.
All settings are loaded from environment variables (.env file).
If .env variable is missing, default values are used.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ------------------------------------------------------------------
# STEP 1: Load .env file
# ------------------------------------------------------------------
# We need to find the .env file which is in the root folder.
# Path(__file__).parent.parent means:
#   __file__  = config/settings.py (this file)
#   .parent   = config/ (folder containing this file)
#   .parent   = quantedge_bot/ (root folder)
# Then we look for .env in that root folder.
ROOT_DIR = Path(__file__).parent.parent
ENV_PATH = ROOT_DIR / ".env"

# Load the .env file. If .env doesn't exist, load_dotenv() silently fails.
load_dotenv(ENV_PATH)


# ------------------------------------------------------------------
# STEP 2: Exchange API Configuration
# ------------------------------------------------------------------
# These are loaded from .env file. If missing, we use empty string.
# We NEVER hardcode real API keys in code.
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

# Trading mode: "paper" = fake money, "live" = real money
TRADING_MODE = os.getenv("TRADING_MODE", "paper")


# ------------------------------------------------------------------
# STEP 3: Trading Configuration
# ------------------------------------------------------------------
# Which cryptocurrencies we will trade.
SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "ADA/USDT",
]

# ------------------------------------------------------------------
# STEP 3B: Per-Asset Timeframes (Research-backed)
# ------------------------------------------------------------------
# Research (Zhivkov & Kandilarov 2026) shows strategy-asset-timeframe
# Per-asset timeframe assignment — requires walk-forward validation.
# These are initial estimates, not research-backed values.

# BTC: 4H - Stable asset, needs longer timeframe for meaningful swings
# ETH: 1H - Moderate volatility, 1H captures pullbacks effectively
# SOL: 4H - High volatility on 1H causes whiplash, 4H smooths noise
# ADA: 1H - Mean-reverting nature works well on shorter timeframe
ASSET_TIMEFRAMES = {
    "BTC/USDT": "4h",
    "ETH/USDT": "1h",
    "SOL/USDT": "4h",
    "ADA/USDT": "1h",
}

# Timeframes for swing trading
PRIMARY_TIMEFRAME = "1h"       # Research-backed (Zhivkov & Kandilarov 2026) Main chart for signals
# Real Binance supports 1000 candles for backtesting
BACKTEST_CANDLE_LIMIT = 1000
CONFIRMATION_TIMEFRAME = "1d"  # Higher timeframe for trend confirmation

# Base currency (what we use to buy crypto)
BASE_CURRENCY = "USDT"


# ------------------------------------------------------------------
# STEP 4: Risk Management Configuration
# ------------------------------------------------------------------
# Portfolio size in USDT (how much money the bot can use)
PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "1000"))

# Maximum risk per trade as a fraction of portfolio (2% = 0.02)
MAX_RISK_PER_TRADE = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))

# Maximum daily loss as a fraction of portfolio (5% = 0.05)
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.05"))

# Maximum number of positions open at the same time
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "4"))

# Stop Loss: How many ATR away from entry
SL_ATR_MULTIPLIER = float(os.getenv("SL_ATR_MULTIPLIER", "2.0"))

# Take Profit: Risk:Reward ratio
TP_RISK_REWARD_RATIO = float(os.getenv("TP_RISK_REWARD_RATIO", "2.5"))


# ------------------------------------------------------------------
# STEP 5: Strategy Parameters
# ------------------------------------------------------------------
# These are the OPTIMIZED parameters from backtesting (Chapter 7).
# Updated from original (RSI<35, Vol>1.5x, ADX>20) to:
# RSI<45, Vol>1.0x, ADX>15 — based on parameter sweep results.
STRATEGY_CONFIG = {
    "ema_fast": 20,
    "ema_slow": 50,
    "rsi_period": 14,
    "rsi_buy_zone": 45,              # Optimized from 35
    "rsi_sell_zone": 70,
    "volume_ma_period": 20,
    "volume_spike_multiplier": 1.0,  # Optimized from 1.5
    "adx_threshold": 20,             # Changed from 15 to 20 (research-based)
    "atr_multiplier": 2.0,           # Now used by strategy
    "risk_reward_ratio": 2.5,        # Now used by strategy
}


# ------------------------------------------------------------------
# STEP 5B: Per-Asset Strategy Parameters (Research-backed)
# ------------------------------------------------------------------
# Research (Zhivkov & Kandilarov 2026) shows strategy-asset interaction
# effects of 2.4x-17.8x in viable parameter space.
# Different assets need different parameters.
ASSET_STRATEGY_CONFIG = {
    "BTC/USDT": {
        "rsi_buy_zone": 50,       # BTC pulls back less — higher RSI acceptance
        "volume_multiplier": 1.5, # BTC has deep liquidity — need strong volume
        "adx_threshold": 30,      # BTC trends strongly — higher ADX for conviction
    },
    "ETH/USDT": {
        "rsi_buy_zone": 42,
        "volume_multiplier": 1.2,
        "adx_threshold": 20,
    },
    "SOL/USDT": {
        "rsi_buy_zone": 45,
        "volume_multiplier": 1.0,
        "adx_threshold": 18,
    },
    "ADA/USDT": {
        "rsi_buy_zone": 35,
        "volume_multiplier": 1.0,
        "adx_threshold": 18,
    },
        "BTC/USDT": {
        "donchian_period": 20,
        "atr_stop_multiplier": 3.0,
        "volume_multiplier": 1.2,
        "adx_threshold": 25,
    },
}

# ------------------------------------------------------------------
# STEP 5b: Per-Symbol Strategy Assignment
# ------------------------------------------------------------------
# RESEARCH BASIS: Brauneis & Mestel (2018) + Zarattini, Pagani & Barbon
# (2025, SSRN 5209907) — BTC is more liquid/efficient than ETH/SOL/ADA,
# so pullback-style entries fit BTC poorly.
SYMBOL_STRATEGY_MAP = {
    "BTC/USDT": "donchian_breakout",
    "ETH/USDT": "swing_combo",
    "SOL/USDT": "swing_combo",
    "ADA/USDT": "swing_combo",
}

# Donchian ensemble lookback periods for BTC (4H candles).
# Starting point — MUST be walk-forward validated.
DONCHIAN_LOOKBACK_PERIODS = [10, 20, 55]

# ------------------------------------------------------------------
# STEP 6: Telegram Notification Configuration
# ------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# ------------------------------------------------------------------
# STEP 7: Logging Configuration
# ------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "bot.log"

# Create logs directory if it doesn't exist
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------
# STEP 8: Database Configuration
# ------------------------------------------------------------------
DATABASE_PATH = ROOT_DIR / "data" / "trading_data.db"