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

# Timeframes for swing trading
PRIMARY_TIMEFRAME = "4h"       # Main chart for signals
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
STRATEGY_CONFIG = {
    "ema_fast": 20,
    "ema_slow": 50,
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 65,
    "volume_ma_period": 20,
    "volume_spike_multiplier": 1.5,
    "adx_threshold": 20,
}


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