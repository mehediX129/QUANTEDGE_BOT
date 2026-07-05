"""
strategies/__init__.py

Strategy registry.
Import and list all available strategies here.
"""

from strategies.swing_strategy import SwingStrategy

# Registry of all available strategies
STRATEGIES = {
    "swing_combo": SwingStrategy,
}

# Default strategy
DEFAULT_STRATEGY = "swing_combo"