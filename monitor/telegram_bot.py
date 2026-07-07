"""
monitor/telegram_bot.py

Telegram notification system for trade alerts.
Sends real-time notifications for signals, trades, and errors.
"""

import requests
from utils.logger import log
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


class TelegramNotifier:
    """Send notifications via Telegram bot."""
    
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id and 
                          "your_telegram_token_here" not in self.token)
        
        if self.enabled:
            log.info("Telegram notifications enabled")
        else:
            log.warning("Telegram not configured — notifications disabled")
    
    def send(self, message: str) -> bool:
        """Send a message. Returns True if successful."""
        if not self.enabled:
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            response = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=5)
            
            if response.status_code == 200:
                log.debug("Telegram notification sent")
                return True
            else:
                log.error(f"Telegram failed: {response.text}")
                return False
        except Exception as e:
            log.error(f"Telegram error: {e}")
            return False
    
    def signal_alert(self, symbol: str, signal: str, entry: float, 
                     stop_loss: float, take_profit: float) -> bool:
        """Send a trading signal alert."""
        emoji = "🟢" if signal == "BUY" else "🔴"
        msg = (
            f"{emoji} <b>{signal} SIGNAL</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Entry:</b> ${entry:,.2f}\n"
            f"<b>Stop Loss:</b> ${stop_loss:,.2f}\n"
            f"<b>Take Profit:</b> ${take_profit:,.2f}"
        )
        return self.send(msg)
    
    def trade_alert(self, symbol: str, action: str, qty: float, price: float) -> bool:
        """Send a trade execution alert."""
        msg = (
            f"✅ <b>TRADE EXECUTED</b>\n"
            f"<b>{action}:</b> {qty:.6f} {symbol}\n"
            f"<b>Price:</b> ${price:,.2f}"
        )
        return self.send(msg)
    
    def error_alert(self, error_msg: str) -> bool:
        """Send an error alert."""
        return self.send(f"🚨 <b>ERROR</b>\n{error_msg}")
    
    def daily_summary(self, pnl: float, trades: int, win_rate: float) -> bool:
        """Send end-of-day summary."""
        msg = (
            f"📊 <b>DAILY SUMMARY</b>\n"
            f"<b>PnL:</b> ${pnl:+.2f}\n"
            f"<b>Trades:</b> {trades}\n"
            f"<b>Win Rate:</b> {win_rate:.1f}%"
        )
        return self.send(msg)