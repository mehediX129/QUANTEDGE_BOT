"""
execution/order_executor.py

Order Execution Engine.
Handles all communication with Binance for order placement,
cancellation, and tracking.

Supports:
- Market Buy/Sell orders
- Stop-Loss orders (Stop-Limit)
- Order status checking
- Precision handling (quantity rounding)
- Error handling with retry
"""

import ccxt
import time
from typing import Optional, Dict, Tuple
from utils.logger import log
from config.settings import (
    BINANCE_API_KEY,
    BINANCE_SECRET_KEY,
    TRADING_MODE,
)


class OrderExecutor:
    """
    Executes orders on Binance exchange.
    
    Responsibilities:
    1. Place market buy/sell orders
    2. Place stop-loss orders
    3. Check order status
    4. Handle quantity precision
    5. Error handling & retry
    
    Usage:
        executor = OrderExecutor()
        order = executor.market_buy("BTC/USDT", 0.001)
        order = executor.market_sell("BTC/USDT", 0.001)
    """
    
    def __init__(self):
        """Initialize connection to Binance."""
        
        self.paper_mode = (TRADING_MODE == "paper")
        
        # Create exchange connection
        self.exchange = ccxt.binance({
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_SECRET_KEY,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        })
        
        # Switch to testnet if paper trading
        if self.paper_mode:
            self.exchange.set_sandbox_mode(True)
            log.info("🔬 OrderExecutor initialized in PAPER mode")
        else:
            log.info("🚀 OrderExecutor initialized in LIVE mode")
        
        # Load market info (precision, limits)
        self.exchange.load_markets()
        
        # Retry settings
        self.max_retries = 3
        self.retry_delay = 2  # seconds
    
    # ------------------------------------------------------------------
    # METHOD 1: Get Symbol Precision
    # ------------------------------------------------------------------
    
    def _get_symbol_info(self, symbol: str) -> Dict:
        """
        Get trading precision and limits for a symbol.
        
        Binance requires quantities rounded to specific decimal places.
        For example, BTC/USDT might need 5 decimal places (0.00001).
        
        Args:
            symbol: Trading pair like 'BTC/USDT'
        
        Returns:
            Dictionary with amount_precision, price_precision, min_notional
        """
        try:
            market = self.exchange.market(symbol)
            return {
                "amount_precision": market["precision"]["amount"],
                "price_precision": market["precision"]["price"],
                "min_notional": market["limits"]["cost"]["min"],
                "min_amount": market["limits"]["amount"]["min"],
            }
        except Exception as e:
            log.error(f"Failed to get symbol info for {symbol}: {e}")
            # Safe defaults
            return {
                "amount_precision": 0.00001,
                "price_precision": 0.01,
                "min_notional": 10.0,
                "min_amount": 0.00001,
            }
    
    # ------------------------------------------------------------------
    # METHOD 2: Round Quantity
    # ------------------------------------------------------------------
    
    def _round_quantity(self, quantity: float, precision: float) -> float:
        """
        Round quantity to exchange-required precision.
        
        Example:
            precision = 0.001 (3 decimal places)
            quantity = 1.23456 → returns 1.234
        
        Args:
            quantity: Raw quantity
            precision: Minimum step size
        
        Returns:
            Rounded quantity
        """
        if precision <= 0:
            return float(int(quantity))
        
        # Calculate decimal places from precision
        decimal_places = len(str(precision).rstrip('0').split('.')[-1])
        rounded = round(quantity - (quantity % precision), decimal_places)
        
        return rounded
    
    # ------------------------------------------------------------------
    # METHOD 3: Market Buy Order
    # ------------------------------------------------------------------
    
    def market_buy(self, symbol: str, quantity: float) -> Optional[Dict]:
        """
        Place a MARKET BUY order.
        
        Buys immediately at the best available ask price.
        
        Args:
            symbol: Trading pair like 'BTC/USDT'
            quantity: Amount to buy (in base currency, e.g., BTC)
        
        Returns:
            Order dictionary if successful, None if failed
        
        Example:
            order = executor.market_buy("BTC/USDT", 0.001)
            # Buys 0.001 BTC at current market price
        """
        
        # Step 1: Get symbol precision
        info = self._get_symbol_info(symbol)
        
        # Step 2: Round quantity
        rounded_qty = self._round_quantity(quantity, info["amount_precision"])
        
        # Step 3: Validate minimum order
        current_price = self.get_current_price(symbol)
        if current_price:
            order_value = rounded_qty * current_price
            if order_value < info["min_notional"]:
                log.error(
                    f"Order value ${order_value:.2f} below minimum "
                    f"${info['min_notional']} for {symbol}"
                )
                return None
        
        # Step 4: Place order with retry
        for attempt in range(1, self.max_retries + 1):
            try:
                log.info(
                    f"🟢 MARKET BUY: {symbol} | "
                    f"Qty: {rounded_qty} | Attempt: {attempt}/{self.max_retries}"
                )
                
                order = self.exchange.create_market_buy_order(
                    symbol=symbol,
                    amount=rounded_qty,
                )
                
                log.success(
                    f"✅ BUY FILLED: {symbol} | "
                    f"Qty: {order['amount']} | "
                    f"Price: ${order['price']:.2f} | "
                    f"Cost: ${order['cost']:.2f}"
                )
                
                return order
                
            except ccxt.InsufficientFunds as e:
                log.error(f"Insufficient funds for {symbol}: {e}")
                return None
                
            except ccxt.InvalidOrder as e:
                log.error(f"Invalid order for {symbol}: {e}")
                return None
                
            except Exception as e:
                log.warning(f"Buy attempt {attempt} failed: {e}")
                if attempt < self.max_retries:
                    log.info(f"Retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    log.error(f"All {self.max_retries} buy attempts failed")
                    return None
        
        return None
    
    # ------------------------------------------------------------------
    # METHOD 4: Market Sell Order
    # ------------------------------------------------------------------
    
    def market_sell(self, symbol: str, quantity: float) -> Optional[Dict]:
        """
        Place a MARKET SELL order.
        
        Sells immediately at the best available bid price.
        
        Args:
            symbol: Trading pair
            quantity: Amount to sell
        
        Returns:
            Order dictionary if successful, None if failed
        """
        
        # Get precision
        info = self._get_symbol_info(symbol)
        rounded_qty = self._round_quantity(quantity, info["amount_precision"])
        
        # Place order with retry
        for attempt in range(1, self.max_retries + 1):
            try:
                log.info(
                    f"🔴 MARKET SELL: {symbol} | "
                    f"Qty: {rounded_qty} | Attempt: {attempt}/{self.max_retries}"
                )
                
                order = self.exchange.create_market_sell_order(
                    symbol=symbol,
                    amount=rounded_qty,
                )
                
                log.success(
                    f"✅ SELL FILLED: {symbol} | "
                    f"Qty: {order['amount']} | "
                    f"Price: ${order['price']:.2f} | "
                    f"Cost: ${order['cost']:.2f}"
                )
                
                return order
                
            except ccxt.InsufficientFunds as e:
                log.error(f"Insufficient funds: {e}")
                return None
                
            except Exception as e:
                log.warning(f"Sell attempt {attempt} failed: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    log.error(f"All {self.max_retries} sell attempts failed")
                    return None
        
        return None
    
    # ------------------------------------------------------------------
    # METHOD 5: Stop-Loss Order (Stop-Limit)
    # ------------------------------------------------------------------
    
    def place_stop_loss(
        self, symbol: str, quantity: float, stop_price: float
    ) -> Optional[Dict]:
        """
        Place a STOP-LOSS order.
        
        When price reaches stop_price, a limit sell order is placed
        at limit_price (slightly below stop for safety).
        
        Args:
            symbol: Trading pair
            quantity: Amount to sell
            stop_price: Trigger price
        
        Returns:
            Order dictionary if successful
        """
        
        info = self._get_symbol_info(symbol)
        rounded_qty = self._round_quantity(quantity, info["amount_precision"])
        
        # Limit price = 2% below stop (ensures fill)
        limit_price = stop_price * 0.98
        limit_price = round(limit_price, 2)
        
        for attempt in range(1, self.max_retries + 1):
            try:
                log.info(
                    f"🛑 STOP LOSS: {symbol} | "
                    f"Qty: {rounded_qty} | "
                    f"Stop: ${stop_price:.2f} | "
                    f"Limit: ${limit_price:.2f}"
                )
                
                order = self.exchange.create_order(
                    symbol=symbol,
                    type="STOP_LOSS_LIMIT",
                    side="sell",
                    amount=rounded_qty,
                    price=limit_price,
                    params={"stopPrice": stop_price},
                )
                
                log.success(f"✅ STOP LOSS placed for {symbol}")
                return order
                
            except Exception as e:
                log.warning(f"Stop-loss attempt {attempt} failed: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    log.error("Stop-loss placement failed")
                    return None
        
        return None
    
    # ------------------------------------------------------------------
    # METHOD 6: Cancel Order
    # ------------------------------------------------------------------
    
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an existing order.
        
        Args:
            order_id: Order ID to cancel
            symbol: Trading pair
        
        Returns:
            True if cancelled successfully
        """
        try:
            self.exchange.cancel_order(order_id, symbol)
            log.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            log.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    # ------------------------------------------------------------------
    # METHOD 7: Get Order Status
    # ------------------------------------------------------------------
    
    def get_order_status(self, order_id: str, symbol: str) -> Optional[Dict]:
        """
        Check the status of an order.
        
        Status types:
        - 'open': Still waiting to fill
        - 'closed': Completely filled
        - 'canceled': Cancelled
        - 'expired': Expired
        
        Args:
            order_id: Order ID
            symbol: Trading pair
        
        Returns:
            Order info dictionary
        """
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            log.debug(f"Order {order_id}: {order['status']}")
            return order
        except Exception as e:
            log.error(f"Failed to fetch order {order_id}: {e}")
            return None
    
    # ------------------------------------------------------------------
    # METHOD 8: Get Current Price
    # ------------------------------------------------------------------
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current market price for a symbol.
        
        Args:
            symbol: Trading pair
        
        Returns:
            Current price or None
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker["last"]
        except Exception as e:
            log.error(f"Failed to get price for {symbol}: {e}")
            return None
    
    # ------------------------------------------------------------------
    # METHOD 9: Get Account Balance
    # ------------------------------------------------------------------
    
    def get_balance(self, currency: str = "USDT") -> float:
        """
        Get available balance for a currency.
        
        Args:
            currency: Currency code (USDT, BTC, etc.)
        
        Returns:
            Available balance
        """
        try:
            balance = self.exchange.fetch_balance()
            free = balance.get(currency, {}).get("free", 0)
            return free
        except Exception as e:
            log.error(f"Failed to get {currency} balance: {e}")
            return 0.0
    
    # ------------------------------------------------------------------
    # METHOD 10: Get Open Positions (Spot Balances)
    # ------------------------------------------------------------------
    
    def get_positions(self) -> Dict[str, float]:
        """
        Get all non-zero cryptocurrency balances.
        
        In spot trading, "positions" are just your coin balances.
        
        Returns:
            Dictionary of {symbol: amount}
        """
        try:
            balance = self.exchange.fetch_balance()
            positions = {}
            
            for currency, data in balance["total"].items():
                if data > 0 and currency != "USDT":
                    positions[currency] = data
            
            return positions
        except Exception as e:
            log.error(f"Failed to fetch positions: {e}")
            return {}