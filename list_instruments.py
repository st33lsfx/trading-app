import os
from dotenv import load_dotenv
from client import Trading212Client

# Load environment variables
load_dotenv()

API_KEY = os.getenv("T212_API_KEY")
BASE_URL = os.getenv("T212_BASE_URL")

def main():
    if not API_KEY:
        print("Error: API Key not found.")
        return

    client = Trading212Client(API_KEY, BASE_URL)
    
    print("Fetching instruments...")
    instruments = client.get_instruments()
    
    # Filter for a few examples of Stocks and ETFs
    stocks = [i for i in instruments if i.get('type') == 'STOCK'][:5]
    etfs = [i for i in instruments if i.get('type') == 'ETF'][:5]
    
    print(f"\nTotal instruments found: {len(instruments)}")
    
    print("\n--- Example Stocks (Akcie) ---")
    for s in stocks:
        print(f"Ticker: {s['ticker']:<12} Name: {s['name']} (Currency: {s['currencyCode']})")

    print("\n--- Example ETFs ---")
    for e in etfs:
        print(f"Ticker: {e['ticker']:<12} Name: {e['name']} (Currency: {e['currencyCode']})")

if __name__ == "__main__":
    main()
