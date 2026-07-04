"""
utils/logger.py

Professional logging setup using loguru.
Provides a configured logger that writes to both console and file.
"""

import sys
from pathlib import Path
from loguru import logger


def setup_logging():
    """
    Configure the logger with proper formatting and file output.
    
    This function:
    1. Removes the default loguru handler
    2. Adds a console handler (colored output for terminal)
    3. Adds a file handler (saves all logs to file)
    4. Returns the configured logger
    """
    
    # Remove the default loguru handler (we will add our own)
    logger.remove()
    
    # ------------------------------------------------------------------
    # Console Handler: Shows logs in terminal with colors
    # ------------------------------------------------------------------
    logger.add(
        sys.stdout,                           # Write to terminal
        format="<green>{time:HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
               "<level>{message}</level>",
        level="INFO",                         # Show INFO and above in console
        colorize=True,                        # Use colors for different levels
    )
    
    # ------------------------------------------------------------------
    # File Handler: Saves all logs to file for debugging
    # ------------------------------------------------------------------
    # We need the logs directory path
    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    logger.add(
        logs_dir / "bot_{time:YYYY-MM-DD}.log",  # New file each day
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | "
               "{level: <8} | "
               "{name}:{function}:{line} | "
               "{message}",
        level="DEBUG",                            # Save ALL levels to file
        rotation="00:00",                         # New file at midnight
        retention="30 days",                      # Keep logs for 30 days
        compression="zip",                        # Compress old log files
        encoding="utf-8",
    )
    
    return logger


# ------------------------------------------------------------------
# Create a global logger instance
# When other files do: from utils.logger import log
# they get a ready-to-use logger
# ------------------------------------------------------------------
log = setup_logging()