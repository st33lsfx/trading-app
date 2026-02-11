"""
Yahoo Finance Ticker Validator
==============================
Check which crypto tickers are available on Yahoo Finance.
"""

import yfinance as yf
import pandas as pd

# All crypto tickers from bot.py
CRYPTO_TICKERS = [
    # TIER 1
    {"yf": "BTC-USD", "name": "Bitcoin"},
    {"yf": "SOL-USD", "name": "Solana"},
    {"yf": "DOGE-USD", "name": "Dogecoin"},
    # TIER 2
    {"yf": "ETH-USD", "name": "Ethereum"},
    {"yf": "XRP-USD", "name": "Ripple"},
    {"yf": "ATOM-USD", "name": "Cosmos"},
    {"yf": "LTC-USD", "name": "Litecoin"},
    {"yf": "RUNE-USD", "name": "THORChain"},
    {"yf": "SEI-USD", "name": "Sei"},
    {"yf": "EGLD-USD", "name": "MultiversX"},
    {"yf": "ZIL-USD", "name": "Zilliqa"},
    {"yf": "CHZ-USD", "name": "Chiliz"},
    # TIER 3
    {"yf": "ADA-USD", "name": "Cardano"},
    {"yf": "AVAX-USD", "name": "Avalanche"},
    {"yf": "DOT-USD", "name": "Polkadot"},
    {"yf": "XLM-USD", "name": "Stellar"},
    {"yf": "VET-USD", "name": "VeChain"},
    {"yf": "GALA-USD", "name": "Gala"},
    {"yf": "ENS-USD", "name": "Ethereum Name Service"},
    {"yf": "SHIB-USD", "name": "Shiba Inu"},
    {"yf": "WLD-USD", "name": "Worldcoin"},
    {"yf": "KAS-USD", "name": "Kaspa"},
    # TIER 4
    {"yf": "SUI-USD", "name": "Sui"},
    {"yf": "ARB-USD", "name": "Arbitrum"},
    {"yf": "PEPE-USD", "name": "Pepe"},
    {"yf": "APE-USD", "name": "ApeCoin"},
    {"yf": "CRV-USD", "name": "Curve DAO"},
    {"yf": "LDO-USD", "name": "Lido DAO"},
    {"yf": "ICP-USD", "name": "Internet Computer"},
    {"yf": "TRX-USD", "name": "Tron"},
    {"yf": "FLOW-USD", "name": "Flow"},
    {"yf": "IMX-USD", "name": "Immutable X"},
]

def check_ticker(ticker_info):
    """Check if ticker exists on Yahoo Finance."""
    symbol = ticker_info["yf"]
    name = ticker_info["name"]
    
    try:
        ticker = yf.Ticker(symbol)
        # Try to get recent data
        hist = ticker.history(period="1d")
        
        if hist.empty:
            return {"symbol": symbol, "name": name, "status": "❌ NO DATA", "price": None}
        else:
            price = hist['Close'].iloc[-1]
            return {"symbol": symbol, "name": name, "status": "✅ OK", "price": f"${price:.2f}"}
    except Exception as e:
        return {"symbol": symbol, "name": name, "status": f"❌ ERROR", "price": str(e)[:50]}

if __name__ == "__main__":
    print("\n" + "="*90)
    print("🔍 YAHOO FINANCE TICKER VALIDATION")
    print("="*90 + "\n")
    
    results = []
    working = []
    failed = []
    
    print(f"Testing {len(CRYPTO_TICKERS)} crypto tickers...\n")
    
    for i, ticker_info in enumerate(CRYPTO_TICKERS, 1):
        print(f"[{i:2d}/{len(CRYPTO_TICKERS)}] Testing {ticker_info['yf']:15s}...", end=" ", flush=True)
        result = check_ticker(ticker_info)
        
        if result["status"] == "✅ OK":
            print(f"✅ OK - {result['price']}")
            working.append(result)
        else:
            print(f"{result['status']}")
            failed.append(result)
        
        results.append(result)
    
    # Summary
    print("\n" + "="*90)
    print(f"📊 SUMMARY")
    print("="*90)
    print(f"✅ Working: {len(working)}/{len(CRYPTO_TICKERS)} ({len(working)/len(CRYPTO_TICKERS)*100:.1f}%)")
    print(f"❌ Failed:  {len(failed)}/{len(CRYPTO_TICKERS)} ({len(failed)/len(CRYPTO_TICKERS)*100:.1f}%)")
    
    if failed:
        print("\n" + "─"*90)
        print("❌ FAILED TICKERS:")
        print("─"*90)
        for f in failed:
            print(f"   {f['symbol']:15s} - {f['name']:25s}")
        
        print("\n💡 SOLUTIONS:")
        print("   1. Remove these from bot.py priority_tickers")
        print("   2. Find alternative Yahoo symbols (e.g., SUI1-USD instead of SUI-USD)")
        print("   3. Use CoinGecko API as fallback for missing tickers")
    
    print("\n" + "="*90 + "\n")
    
    # Save results
    df = pd.DataFrame(results)
    df.to_csv("/tmp/ticker_validation.csv", index=False)
    print(f"💾 Results saved to: /tmp/ticker_validation.csv\n")
