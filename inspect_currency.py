import os
from dotenv import load_dotenv
from client import Trading212Client

load_dotenv()
API_KEY = os.getenv("T212_API_KEY")
BASE_URL = os.getenv("T212_BASE_URL")

client = Trading212Client(API_KEY, BASE_URL)
instruments = client.get_instruments()

# Find C024l_EQ or similar UK stocks
uk_stocks = [i for i in instruments if "UK" in i['ticker'] or i.get('currencyCode') == 'GBP']

print(f"Found {len(uk_stocks)} UK/GBP instruments.")
if uk_stocks:
    print("Example 1:", uk_stocks[0])
    
# Check C024 specifically if possible, or similar
target = next((i for i in instruments if "C024" in i['ticker']), None)
if target:
    print("Target C024:", target)
else:
    print("C024 not found in list.")
