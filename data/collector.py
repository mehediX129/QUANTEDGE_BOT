"""
data/collector.py

Market data collection module.
Handles all communication with Binance exchange:
- Fetching current prices
- Fetching OHLCV (candlestick) data
- Fetching account balances
"""

import ccxt
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from utils.logger import log
from config.settings import (
    BINANCE_API_KEY,
    BINANCE_SECRET_KEY,
    TRADING_MODE,
    SYMBOLS,
    PRIMARY_TIMEFRAME,
)


class DataCollector:
    """
    Main class for collecting market data from Binance.
    
    This class handles:
    - Exchange connection (real or testnet)
    - Price fetching
    - OHLCV data fetching
    - Balance checking
    
    Usage:
        collector = DataCollector()
        price = collector.get_current_price("BTC/USDT")
        candles = collector.fetch_ohlcv("BTC/USDT", "4h", limit=100)
    """
    
    def __init__(self):
        """
        Initialize the DataCollector.
        
        Creates a connection to Binance exchange.
        If TRADING_MODE is 'paper', connects to testnet (fake money).
        If TRADING_MODE is 'live', connects to real Binance.
        """
        
        # Determine if we are in paper trading mode
        self.paper_mode = (TRADING_MODE == "paper")
        
        # ------------------------------------------------------------------
        # Create the exchange object
        # ------------------------------------------------------------------
        # ccxt.binance() creates a Binance exchange instance.
        # We pass API keys and configuration as a dictionary.
        self.exchange = ccxt.binance({
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_SECRET_KEY,
            "enableRateLimit": True,   # Auto-wait for rate limits
            "options": {
                "defaultType": "spot", # We trade spot, not futures
            },
        })
        
        # ------------------------------------------------------------------
        # Sandbox mode (Testnet)
        # ------------------------------------------------------------------
        # If we are in paper mode, switch to testnet URLs.
        # This means all API calls go to testnet.binance.vision
        # instead of api.binance.com
        if self.paper_mode:
            self.exchange.set_sandbox_mode(True)
            log.info("🔬 DataCollector initialized in PAPER mode (Binance Testnet)")
        else:
            log.info("🚀 DataCollector initialized in LIVE mode (Real Binance)")
        
        # Store which symbols we trade
        self.symbols = SYMBOLS
        
        # Load markets info (available trading pairs, limits, precision)
        self._load_markets()
    
    def _load_markets(self):
        """
        Load market information from the exchange.
        
        This tells us:
        - Which trading pairs are available
        - What is the minimum order size
        - What is the price precision (decimal places)
        - Trading fees
        """
        try:
            log.info("Loading market information from exchange...")
            self.exchange.load_markets()
            log.success(f"Loaded {len(self.exchange.markets)} trading pairs")
        except Exception as e:
            log.error(f"Failed to load markets: {e}")
            raise
    
    # ------------------------------------------------------------------
    # METHOD 1: Get Current Price
    # ------------------------------------------------------------------
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Fetch the current market price for a symbol.
        
        Args:
            symbol: Trading pair like 'BTC/USDT'
        
        Returns:
            Current price as float, or None if error
        
        Example:
            price = collector.get_current_price("BTC/USDT")
            # Returns: 42150.5
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            price = ticker["last"]
            log.debug(f"Price for {symbol}: {price}")
            return price
        except Exception as e:
            log.error(f"Error fetching price for {symbol}: {e}")
            return None
    
    # ------------------------------------------------------------------
    # METHOD 2: Get Current Prices for All Symbols
    # ------------------------------------------------------------------
    
    def get_all_prices(self) -> Dict[str, Optional[float]]:
        """
        Fetch current prices for all configured symbols.
        
        Returns:
            Dictionary like {'BTC/USDT': 42150.5, 'ETH/USDT': 2450.0}
        """
        prices = {}
        for symbol in self.symbols:
            prices[symbol] = self.get_current_price(symbol)
        return prices
    
    # ------------------------------------------------------------------
    # METHOD 3: Fetch OHLCV (Candlestick) Data
    # ------------------------------------------------------------------
    
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = None,
        limit: int = 100,
        since_days: int = None
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV (Open, High, Low, Close, Volume) candlestick data.
        
        Args:
            symbol: Trading pair like 'BTC/USDT'
            timeframe: Candle timeframe ('1m', '5m', '1h', '4h', '1d')
                      If None, uses PRIMARY_TIMEFRAME from settings
            limit: Number of candles to fetch (max 1000)
            since_days: Alternative to limit - fetch candles from X days ago
        
        Returns:
            Pandas DataFrame with columns:
            timestamp, open, high, low, close, volume
        
        Example:
            df = collector.fetch_ohlcv("BTC/USDT", "4h", limit=50)
            print(df.head())
            #    timestamp    open    high    low    close    volume
            # 0  2024-01-15  42100  42500  41900  42350   125.5
        """
        
        # Use default timeframe if not specified
        if timeframe is None:
            timeframe = PRIMARY_TIMEFRAME
        
        try:
            # ------------------------------------------------------------------
            # Calculate 'since' timestamp if since_days is provided
            # ------------------------------------------------------------------
            since = None
            if since_days is not None:
                since = int((datetime.now() - timedelta(days=since_days)).timestamp() * 1000)
                # * 1000 because ccxt uses milliseconds
                # Python's timestamp() gives seconds, so convert to ms
            
            # ------------------------------------------------------------------
            # Fetch candles from exchange
            # ------------------------------------------------------------------
            # fetch_ohlcv() returns a list of lists:
            # [[timestamp, open, high, low, close, volume], ...]
            candles = self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                since=since,
            )
            
            # ------------------------------------------------------------------
            # Convert to Pandas DataFrame
            # ------------------------------------------------------------------
            df = pd.DataFrame(
                candles,
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            
            # ------------------------------------------------------------------
            # Clean up the data
            # ------------------------------------------------------------------
            # Convert millisecond timestamp to datetime
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

            # Add symbol column
            df["symbol"] = symbol
            
            # Sort by timestamp (oldest first)
            df = df.sort_values("timestamp")
            
            # Reset index (0, 1, 2, ...) — timestamp stays as regular column
            df = df.reset_index(drop=True)
            
            log.debug(f"Fetched {len(df)} candles for {symbol} ({timeframe})")
            
            return df
            
        except Exception as e:
            log.error(f"Error fetching OHLCV for {symbol}: {e}")
            return None
    
    # ------------------------------------------------------------------
    # METHOD 4: Fetch Multiple Symbols' OHLCV
    # ------------------------------------------------------------------
    
    def fetch_all_ohlcv(
        self,
        timeframe: str = None,
        limit: int = 1000
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch OHLCV data for all configured symbols.
        
        Returns:
            Dictionary mapping symbol -> DataFrame
        """
        all_data = {}
        for symbol in self.symbols:
            df = self.fetch_ohlcv(symbol, timeframe, limit)
            if df is not None:
                all_data[symbol] = df
            else:
                log.warning(f"Skipping {symbol} due to fetch error")
        return all_data
    
    # ------------------------------------------------------------------
    # METHOD 5: Get Account Balance
    # ------------------------------------------------------------------
    
    def get_balance(self) -> Optional[Dict]:
        """
        Fetch account balance from exchange.
        
        Returns:
            Dictionary with 'free', 'used', 'total' balances
            for each currency.
        """
        try:
            balance = self.exchange.fetch_balance()
            log.debug(f"Balance fetched successfully")
            return balance
        except Exception as e:
            log.error(f"Error fetching balance: {e}")
            return None
    
    # ------------------------------------------------------------------
    # METHOD 6: Get 24hr Ticker Statistics
    # ------------------------------------------------------------------
    
    def get_ticker_24h(self, symbol: str) -> Optional[Dict]:
        """
        Get 24-hour statistics for a symbol.
        
        Returns:
            Dictionary with:
            - last: last price
            - change: price change
            - percentage: change percentage
            - high: 24h high
            - low: 24h low
            - volume: 24h volume in base currency
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                "symbol": symbol,
                "last": ticker["last"],
                "change": ticker["change"],
                "percentage": ticker["percentage"],
                "high": ticker["high"],
                "low": ticker["low"],
                "volume": ticker["baseVolume"],
            }
        except Exception as e:
            log.error(f"Error fetching ticker for {symbol}: {e}")
            return None
    
    # ------------------------------------------------------------------
    # METHOD 7: Get Exchange Status
    # ------------------------------------------------------------------

    def check_exchange_status(self) -> bool:
        """
        Check if the exchange is online and responsive.

        Instead of fetch_status() (which doesn't work on testnet),
        we try to fetch a ticker price — if it works, exchange is online.

        Returns:
            True if exchange is healthy, False otherwise
        """
        try:
            # Test by fetching BTC/USDT price
            # If this works, the exchange is online
            ticker = self.exchange.fetch_ticker("BTC/USDT")

            if ticker and ticker.get("last"):
                log.info(f"✓ Exchange is online (BTC/USDT: ${ticker['last']:,.2f})")
                return True
            else:
                log.warning("Exchange returned unexpected response")
                return False

        except Exception as e:
            log.error(f"Exchange health check failed: {e}")
            return False