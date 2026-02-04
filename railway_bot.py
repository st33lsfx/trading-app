"""
Lightweight Trading Bot for Railway (24/7)
No Streamlit UI = Low memory (~50-100MB)
"""
import os
import time
import signal
import sys

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from bot import TradingBot

# Configuration
BROKER = "capital"  # or "t212"

def get_env(key, default=None):
    """Get environment variable."""
    return os.getenv(key, default)

def main():
    print("=" * 50)
    print("🚀 Trading Bot Starting (Railway Mode)")
    print("=" * 50)
    
    # Load credentials
    if BROKER == "capital":
        api_key = get_env("CAPITAL_API_KEY")
        login = get_env("CAPITAL_LOGIN")
        password = get_env("CAPITAL_PASSWORD")
        base_url = get_env("CAPITAL_BASE_URL", "https://demo-api-capital.backend-capital.com")
        
        if not all([api_key, login, password]):
            print("❌ Missing Capital.com credentials!")
            print("Set: CAPITAL_API_KEY, CAPITAL_LOGIN, CAPITAL_PASSWORD")
            sys.exit(1)
        
        bot = TradingBot(api_key, base_url, broker="capital", cap_login=login, cap_pass=password)
        print(f"✅ Connected to Capital.com ({base_url})")
        
    else:
        api_key = get_env("T212_API_KEY")
        base_url = get_env("T212_BASE_URL")
        
        if not api_key:
            print("❌ Missing T212 credentials!")
            sys.exit(1)
            
        bot = TradingBot(api_key, base_url, broker="t212")
        print(f"✅ Connected to Trading 212")
    
    # Configure bot for Railway (memory efficient)
    bot.trade_amount = float(get_env("TRADE_AMOUNT", "4.0"))
    bot.max_positions = int(get_env("MAX_POSITIONS", "3"))
    bot.max_daily_loss = float(get_env("MAX_DAILY_LOSS", "8.0"))
    bot.daily_profit_target = float(get_env("DAILY_PROFIT_TARGET", "4.0"))
    bot.small_account_mode = True
    
    print(f"📊 Config: ${bot.trade_amount}/trade, max {bot.max_positions} positions")
    print(f"🛡️ Risk: Max loss ${bot.max_daily_loss}, Target ${bot.daily_profit_target}")
    print("-" * 50)
    
    # Graceful shutdown handler
    def shutdown(signum, frame):
        print("\n⏹️ Shutting down gracefully...")
        bot.stop_loop()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    
    # Start the bot
    bot.start_loop()
    
    # Keep alive and log status periodically
    try:
        while True:
            time.sleep(60)  # Status update every minute
            
            # Log basic status
            positions = len(getattr(bot, 'cached_positions', []))
            daily_pnl = getattr(bot, 'daily_pnl', 0)
            status = "🟢 Running" if bot.is_running else "🔴 Stopped"
            
            print(f"[{time.strftime('%H:%M')}] {status} | Positions: {positions} | Daily P&L: ${daily_pnl:+.2f}")
            
            # Check if bot stopped itself (daily limits)
            if not bot.is_running:
                reason = getattr(bot, 'session_stopped_reason', None)
                if reason:
                    print(f"⚠️ Bot stopped: {reason}")
                    # Wait until next day to restart
                    print("💤 Waiting for next trading day...")
                    time.sleep(3600)  # Check every hour
                    
    except KeyboardInterrupt:
        shutdown(None, None)

if __name__ == "__main__":
    main()
