"""
Focused Crypto Backtest
========================
Test only TOP performers from previous backtest.
Exclude: ETH, XRP, DOGE (poor results)
"""

import sys
sys.path.append('/Users/ondrej/Desktop/Weby/Aplikace/Trading app/trading-app')

from backtest import Backtester
import numpy as np

# TOP PERFORMERS from previous backtest
top_crypto = [
    "BNB-USD",    # +39.5%, PF 1.91
    "LTC-USD",    # +36.4%, PF 1.63
    "SOL-USD",    # +29.2%, PF 1.44
    "ADA-USD",    # Moderate
    "AVAX-USD",   # Moderate
    "DOT-USD",    # Small positive
]

# Also test a few more to find hidden gems
additional_crypto = [
    "BTC-USD",    # Must test
    "ATOM-USD",
    "XLM-USD",
]

all_assets = top_crypto + additional_crypto

print("\n" + "="*80)
print("🚀 OPTIMIZED CRYPTO BACKTEST")
print("="*80)
print(f"Assets: {len(all_assets)} (top performers only)")
print(f"Period: 60 days, 15min interval")
print(f"Strategy: Elite Volume Profile v6.0")
print("="*80 + "\n")

bt = Backtester()
results = []

for i, ticker in enumerate(all_assets, 1):
    bt.ticker = ticker
    print(f"[{i:2d}/{len(all_assets)}] Testing {ticker:12s}...", end=" ", flush=True)
    
    try:
        res = bt.run(ticker, period="60d", interval="15m")
        
        if 'error' in res:
            print(f"❌ FAIL: {res['error']}")
        else:
            wr = res['win_rate']
            pf = res['profit_factor']
            ret = res['total_return_pct']
            trades = res['total_trades']
            
            # Color coding
            if pf >= 1.5:
                emoji = "🟢"
            elif pf >= 1.0:
                emoji = "🟡"
            else:
                emoji = "🔴"
                
            print(f"{emoji} WR: {wr:5.1f}% | PF: {pf:4.2f} | Ret: {ret:+7.2f}% | Trades: {trades}")
            results.append(res)
    except Exception as e:
        print(f"💥 ERROR: {e}")

# Summary
print("\n" + "="*80)
print("📊 SUMMARY")
print("="*80)

if results:
    # Sort by profit factor
    results.sort(key=lambda x: x.get('profit_factor', 0), reverse=True)
    
    total_return = sum([r['total_return_pct'] for r in results])
    avg_pf = np.mean([r['profit_factor'] for r in results if r['profit_factor'] < 100])
    avg_wr = np.mean([r['win_rate'] for r in results])
    total_trades = sum([r['total_trades'] for r in results])
    
    print(f"Total Return: {total_return:+.2f}%")
    print(f"Avg Profit Factor: {avg_pf:.2f}")
    print(f"Avg Win Rate: {avg_wr:.1f}%")
    print(f"Total Trades: {total_trades}")
    
    print("\n" + "─"*80)
    print("🏆 TOP 5 PERFORMERS:")
    print("─"*80)
    for i, r in enumerate(results[:5], 1):
        print(f"{i}. {r['ticker']:12s} | Ret: {r['total_return_pct']:+7.2f}% | "
              f"PF: {r['profit_factor']:4.2f} | WR: {r['win_rate']:5.1f}% | "
              f"Trades: {r['total_trades']}")
    
    print("\n" + "─"*80)
    print("🗑️  BOTTOM PERFORMERS (consider blacklisting):")
    print("─"*80)
    for i, r in enumerate(results[-3:], 1):
        if r['profit_factor'] < 1.0:
            print(f"❌ {r['ticker']:12s} | Ret: {r['total_return_pct']:+7.2f}% | "
                  f"PF: {r['profit_factor']:4.2f} | WR: {r['win_rate']:5.1f}%")
    
    # Recommendations
    print("\n" + "="*80)
    print("💡 RECOMMENDATIONS")
    print("="*80)
    
    winners = [r for r in results if r['profit_factor'] >= 1.3]
    losers = [r for r in results if r['profit_factor'] < 0.9]
    
    print(f"\n✅ FOCUS ON ({len(winners)} assets with PF ≥ 1.3):")
    for r in winners:
        print(f"   - {r['ticker']}")
    
    if losers:
        print(f"\n❌ BLACKLIST ({len(losers)} assets with PF < 0.9):")
        for r in losers:
            print(f"   - {r['ticker']}")
    
    print("\n" + "="*80 + "\n")
else:
    print("No valid results.\n")
