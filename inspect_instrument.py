import os
import json
from dotenv import load_dotenv
from client import Trading212Client

load_dotenv()
API_KEY = os.getenv("T212_API_KEY")
BASE_URL = os.getenv("T212_BASE_URL")

client = Trading212Client(API_KEY, BASE_URL)
instruments = client.get_instruments()

# Find examples: one US, one German (DE), one UK
us_sample = next((i for i in instruments if i['ticker'].endswith('_US_EQ')), None)
de_sample = next((i for i in instruments if i['ticker'].endswith('_DE_EQ')), None)
uk_sample = next((i for i in instruments if i['ticker'].endswith('_UK_EQ') or i['currencyCode'] == 'GBP'), None) # UK tickers might vary

print("--- US Sample ---")
print(json.dumps(us_sample, indent=2))

print("\n--- DE Sample ---")
print(json.dumps(de_sample, indent=2))

print("\n--- UK/GBP Sample ---")
print(json.dumps(uk_sample, indent=2))
