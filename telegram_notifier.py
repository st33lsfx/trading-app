"""
Telegram Notifications Module
=============================
Send trade notifications to Telegram bot.

Setup:
1. Create bot via @BotFather
2. Get your chat_id via @userinfobot
3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env or Streamlit secrets
"""

import os
import requests
from datetime import datetime

class TelegramNotifier:
    def __init__(self, token=None, chat_id=None):
        self.token = token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = bool(self.token and self.chat_id)
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else None
    
    def send_message(self, text, parse_mode="HTML"):
        """Send a message to Telegram."""
        if not self.enabled:
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def notify_trade(self, direction, ticker, qty, price, sl=None, tp=None):
        """
        Send trade notification.
        
        Args:
            direction: "BUY" or "SELL"
            ticker: Asset symbol
            qty: Quantity
            price: Entry price
            sl: Stop loss price
            tp: Take profit price
        """
        emoji = "🟢" if direction == "BUY" else "🔴"
        
        message = f"""
{emoji} <b>NEW TRADE</b>

<b>Direction:</b> {direction}
<b>Asset:</b> {ticker}
<b>Quantity:</b> {qty}
<b>Entry:</b> ${price:.4f}
<b>SL:</b> ${sl:.4f if sl else 'N/A'}
<b>TP:</b> ${tp:.4f if tp else 'N/A'}

<i>⏱️ {datetime.now().strftime('%H:%M:%S')}</i>
"""
        return self.send_message(message)
    
    def notify_close(self, ticker, pnl, reason=""):
        """Notify when a trade is closed."""
        emoji = "✅" if pnl >= 0 else "❌"
        pnl_text = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        
        message = f"""
{emoji} <b>TRADE CLOSED</b>

<b>Asset:</b> {ticker}
<b>P&L:</b> <code>{pnl_text}</code>
<b>Reason:</b> {reason or 'SL/TP Hit'}

<i>⏱️ {datetime.now().strftime('%H:%M:%S')}</i>
"""
        return self.send_message(message)
    
    def send_daily_report(self, total_trades, wins, losses, pnl, balance):
        """Send daily summary report."""
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        
        message = f"""
📊 <b>DAILY REPORT</b>

{pnl_emoji} <b>P&L:</b> <code>{"+" if pnl >= 0 else ""}{pnl:.2f} USD</code>
💰 <b>Balance:</b> ${balance:.2f}

📈 <b>Trades:</b> {total_trades}
✅ <b>Wins:</b> {wins}
❌ <b>Losses:</b> {losses}
🎯 <b>Win Rate:</b> {win_rate:.1f}%

<i>📅 {datetime.now().strftime('%Y-%m-%d')}</i>
"""
        return self.send_message(message)
    
    def notify_error(self, error_msg):
        """Notify about errors/issues."""
        message = f"""
⚠️ <b>BOT ALERT</b>

{error_msg}

<i>⏱️ {datetime.now().strftime('%H:%M:%S')}</i>
"""
        return self.send_message(message)

    def notify_drawdown_alert(self, drawdown_pct, balance, initial_balance, threshold):
        """v3.3: Send drawdown warning alert."""
        message = f"""
⚠️ <b>DRAWDOWN ALERT</b>

📉 <b>Drawdown:</b> <code>-{drawdown_pct:.1f}%</code>
💰 <b>Balance:</b> {balance:.0f} CZK
📊 <b>Initial:</b> {initial_balance:.0f} CZK
🎯 <b>Threshold:</b> {threshold:.0f}%

<i>Bot continues trading. Monitor closely.</i>
<i>⏱️ {datetime.now().strftime('%H:%M:%S')}</i>
"""
        return self.send_message(message)

    def notify_emergency_stop(self, drawdown_pct, balance):
        """v3.3: Send emergency stop alert."""
        message = f"""
🚨 <b>EMERGENCY STOP</b>

📉 <b>Drawdown:</b> <code>-{drawdown_pct:.1f}%</code>
💰 <b>Balance:</b> {balance:.0f} CZK
🛑 <b>All trading stopped!</b>

Manual intervention required to resume.
<i>⏱️ {datetime.now().strftime('%H:%M:%S')}</i>
"""
        return self.send_message(message)

    def notify_auto_pause(self, consecutive_losses, wins, losses):
        """v3.3: Send auto-pause notification."""
        message = f"""
🛑 <b>AUTO-PAUSE</b>

{consecutive_losses} consecutive losses detected.
Trading paused until manual resume.

📊 <b>Session:</b> {wins}W / {losses}L

<i>⏱️ {datetime.now().strftime('%H:%M:%S')}</i>
"""
        return self.send_message(message)


# Singleton instance
_notifier = None

def get_telegram_notifier(token=None, chat_id=None):
    """Get or create Telegram notifier instance."""
    global _notifier
    if _notifier is None or token or chat_id:
        _notifier = TelegramNotifier(token, chat_id)
    return _notifier
