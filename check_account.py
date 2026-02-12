"""
Check Capital.com Account & Positions
======================================
Verify account balance and open positions.
"""

import os
from dotenv import load_dotenv
from capital_client import CapitalClient

load_dotenv()

# Initialize Capital.com client
api_key = os.getenv("CAPITAL_API_KEY")
login = os.getenv("CAPITAL_LOGIN")
password = os.getenv("CAPITAL_PASSWORD")
live_url = os.getenv("CAPITAL_LIVE_URL", "https://api-capital.backend-capital.com")

print(f"\n{'='*60}")
print(f"CAPITAL.COM LIVE ACCOUNT CHECK")
print(f"{'='*60}\n")

client = CapitalClient(api_key, login, password, live_url)

# 1. Account Info
print("📊 ACCOUNT INFO:")
print("-" * 60)
acc = client.get_account_info()
if acc and 'accounts' in acc and len(acc['accounts']) > 0:
    account = acc['accounts'][0]
    balance_data = account.get('balance', {})
    
    balance = balance_data.get('balance', 0)
    deposit = balance_data.get('deposit', 0)
    profit_loss = balance_data.get('profitLoss', 0)
    available = balance_data.get('available', 0)
    
    print(f"Balance: ${balance:.2f}")
    print(f"Available: ${available:.2f}")
    print(f"Deposits: ${deposit:.2f}")
    print(f"P&L: ${profit_loss:.2f}")
    print(f"Currency: {account.get('currency', 'USD')}")
else:
    print("❌ Failed to get account info")

# 2. Open Positions
print(f"\n📈 OPEN POSITIONS:")
print("-" * 60)
# Fix: correct method name is get_positions
positions = client.get_positions()
if positions:
    pos_list = positions
    if len(pos_list) == 0:
        print("No open positions")
    else:
        for i, pos in enumerate(pos_list, 1):
            market = pos.get('market', {})
            direction = pos.get('direction', 'N/A')
            size = pos.get('size', 0)
            epic = market.get('epic', 'N/A')
            level = pos.get('level', 0)
            pnl = pos.get('profit', 0)
            
            print(f"{i}. {epic} | {direction} | Size: {size} | Entry: ${level:.5f} | P&L: ${pnl:.2f}")
else:
    print("No open positions (or failed to fetch)")

# 3. Recent Orders/Deals
print(f"\n📋 RECENT ACTIVITY (last 50):")
print("-" * 60)
try:
    activity = client.get_activity()
    if activity and 'activities' in activity:
        activities = activity['activities'][:5]  # Show last 5
        for i, act in enumerate(activities, 1):
            deal_ref = act.get('dealReference', 'N/A')
            epic = act.get('epic', 'N/A')
            direction = act.get('direction', 'N/A')
            status = act.get('status', 'N/A')
            action_type = act.get('type', 'N/A')
            timestamp = act.get('date', 'N/A')
            
            print(f"{i}. {timestamp} | {epic} | {direction} {action_type} | Status: {status} | Deal: {deal_ref[:20]}...")
    else:
        print("No recent activity")
except Exception as e:
    print(f"⚠️ Activity check failed: {e}")

print(f"\n{'='*60}\n")
