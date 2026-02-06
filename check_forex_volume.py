
import yfinance as yf

ticker = "EURUSD=X"
print(f"Fetching {ticker}...")
df = yf.Ticker(ticker).history(period="5d", interval="15m")
print(df.head())
print(f"\nTotal Volume: {df['Volume'].sum()}")
if df['Volume'].sum() == 0:
    print("❌ Volume is ZERO. VP Strategy will fail.")
else:
    print("✅ Volume exists.")
