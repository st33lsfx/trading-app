"""
Quick CZK/USD Rate Check
=========================
Verify current exchange rate for accurate position sizing.
"""

import requests

# Get current USD/CZK rate
response = requests.get("https://api.exchangerate-api.com/v4/latest/USD")
data = response.json()
current_rate = data['rates'].get('CZK', 23.0)

print(f"\n{'='*60}")
print(f"💱 USD/CZK EXCHANGE RATE CHECK")
print(f"{'='*60}")
print(f"Current rate: 1 USD = {current_rate:.2f} CZK")
print(f"Bot configured: 1 USD = 23.0 CZK")
print(f"Difference: {abs(current_rate - 23.0):.2f} CZK ({abs(current_rate - 23.0)/23.0*100:.1f}%)")

if abs(current_rate - 23.0) > 1.0:
    print(f"\n⚠️  WARNING: Rate difference > 1 CZK!")
    print(f"   Update in bot.py line 40:")
    print(f"   USD_TO_CZK_RATE = {current_rate:.1f}")
else:
    print(f"\n✅ Rate is OK (difference < 1 CZK)")

print(f"\n📊 Impact on 2000 CZK capital:")
print(f"   With bot rate (23.0): {2000/23.0:.2f} USD")
print(f"   With current rate ({current_rate:.2f}): {2000/current_rate:.2f} USD")
print(f"{'='*60}\n")
