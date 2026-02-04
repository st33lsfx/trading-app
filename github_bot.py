"""
Trading Bot for GitHub Actions (Free 24/7)
Runs single scan cycle every 10 minutes via cron
"""
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()

from capital_client import CapitalClient
from strategy import Strategy
from mean_reversion_strategy import MeanReversionStrategy

# Configuration
BROKER = "capital"
MAX_POSITIONS = 3
TRADE_AMOUNT = 4.0  # USD per trade

def get_env(key, default=None):
    return os.getenv(key, default)

def main():
    print("=" * 50)
    print("🤖 GitHub Actions Trading Bot")
    print(f"⏰ Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 50)
    
    # Connect to broker
    api_key = get_env("CAPITAL_API_KEY")
    login = get_env("CAPITAL_LOGIN")
    password = get_env("CAPITAL_PASSWORD")
    base_url = get_env("CAPITAL_BASE_URL", "https://demo-api-capital.backend-capital.com")
    
    if not all([api_key, login, password]):
        print("❌ Missing credentials! Set GitHub Secrets.")
        sys.exit(1)
    
    try:
        client = CapitalClient(api_key, login, password, base_url)
        print("✅ Connected to Capital.com")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)
    
    # Check account
    try:
        acc = client.get_account_info()
        if acc and 'accounts' in acc:
            balance = acc['accounts'][0].get('balance', {})
            available = balance.get('available', 0)
            total = balance.get('balance', 0)
            print(f"💰 Balance: ${total:.2f} | Available: ${available:.2f}")
    except Exception as e:
        print(f"⚠️ Could not fetch account: {e}")
    
    # Check current positions
    positions = client.get_positions()
    print(f"📊 Open positions: {len(positions)}")
    
    if len(positions) >= MAX_POSITIONS:
        print(f"⏸️ Max positions ({MAX_POSITIONS}) reached. Skipping scan.")
        print("✅ Cycle complete (no action needed)")
        return
    
    # Priority tickers for scanning
    tickers = [
        {"epic": "ETHUSD", "yf": "ETH-USD", "name": "Ethereum"},
        {"epic": "SOLUSD", "yf": "SOL-USD", "name": "Solana"},
        {"epic": "GBPUSD", "yf": "GBPUSD=X", "name": "GBP/USD"},
        {"epic": "AUDUSD", "yf": "AUDUSD=X", "name": "AUD/USD"},
        {"epic": "NZDUSD", "yf": "NZDUSD=X", "name": "NZD/USD"},
        {"epic": "AMD", "yf": "AMD", "name": "AMD"},
        {"epic": "NVDA", "yf": "NVDA", "name": "NVIDIA"},
        {"epic": "TSLA", "yf": "TSLA", "name": "Tesla"},
    ]
    
    # Skip tickers we already have positions in
    open_epics = []
    for p in positions:
        market = p.get('market', {})
        pos = p.get('position', {})
        epic = market.get('epic') or pos.get('epic', '')
        open_epics.append(epic)
    
    # Mean Reversion Strategy
    strategy = MeanReversionStrategy()
    
    trades_made = 0
    
    print("-" * 50)
    print("🔍 Scanning markets...")
    
    for ticker in tickers:
        if ticker['epic'] in open_epics:
            print(f"⏭️ {ticker['name']}: Already have position")
            continue
        
        if len(positions) + trades_made >= MAX_POSITIONS:
            print(f"⏸️ Max positions reached")
            break
        
        try:
            # Fetch data
            strat = Strategy(ticker['yf'])
            df = strat.fetch_data(period="1mo", interval="1h")
            
            if df.empty:
                print(f"⚠️ {ticker['name']}: No data")
                continue
            
            # Get signal
            result = strategy.get_signal(df)
            signal = result.get('signal')
            rsi = result.get('rsi', 50)
            reason = result.get('reason', '')
            
            print(f"📈 {ticker['name']}: {signal} (RSI: {rsi:.1f}) - {reason}")
            
            if signal in ['BUY', 'SELL']:
                # Get price and calculate size
                last_price = df.iloc[-1]['Close']
                
                # Get instrument info
                try:
                    inst_info = client.get_instrument_info(ticker['epic'])
                    min_size = inst_info.get('min_size', 0.1)
                except:
                    min_size = 0.1
                
                # Calculate size
                qty = max(min_size, round(TRADE_AMOUNT / last_price, 3))
                
                # Get SL/TP from strategy
                sl = result.get('sl')
                tp = result.get('tp')
                
                print(f"🎯 Placing {signal} order: {qty} {ticker['epic']} @ ${last_price:.4f}")
                print(f"   SL: {sl}, TP: {tp}")
                
                try:
                    order = client.place_market_order(
                        ticker['epic'],
                        qty,
                        direction=signal,
                        stop_loss=sl,
                        take_profit=tp
                    )
                    print(f"✅ Order confirmed: {order.get('dealReference', 'OK')}")
                    trades_made += 1
                except Exception as e:
                    print(f"❌ Order failed: {e}")
            
            time.sleep(1)  # Rate limiting
            
        except Exception as e:
            print(f"⚠️ {ticker['name']}: Error - {e}")
            continue
    
    print("-" * 50)
    print(f"✅ Cycle complete | Trades: {trades_made} | Positions: {len(positions) + trades_made}")

if __name__ == "__main__":
    main()
