
from backtest import Backtester
import pandas as pd

# Elite 15 Assets
tickers = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
    "NZDUSD=X", "USDCHF=X", "EURGBP=X", "GBPJPY=X", "EURJPY=X"
]

print(f"=== BACKTESTING ELITE STRATEGY (15m, 60d) ===")
print(f"Assets: {len(tickers)}")

bt = Backtester(initial_capital=10000)
results = []    

for ticker in tickers:
    print(f"Testing {ticker}...", end=" ", flush=True)
    try:
        res = bt.run(ticker, period="60d", interval="15m")
        if "error" in res:
            print(f"❌ {res['error']}")
        else:
            print(f"✅ PF: {res['profit_factor']} | WR: {res['win_rate']}% | Trades: {res['total_trades']}")
            results.append(res)
    except Exception as e:
        print(f"❌ Exception: {e}")

# Summary
if results:
    print("\n=== SUMMARY ===")
    df = pd.DataFrame(results)
    df = df[['ticker', 'profit_factor', 'win_rate', 'total_trades', 'total_return_pct', 'max_drawdown_pct']]
    print(df.sort_values(by='profit_factor', ascending=False))
    
    avg_pf = df['profit_factor'].mean()
    total_ret = df['total_return_pct'].sum()
    print(f"\nAverage PF: {avg_pf:.2f}")
    print(f"Total Return (Portfolio): {total_ret:.2f}%")
else:
    print("No valid results.")
