import os
from dotenv import load_dotenv
from capital_client import CapitalClient

load_dotenv()
API_KEY = os.getenv("CAPITAL_API_KEY")
LOGIN = os.getenv("CAPITAL_LOGIN")
PASS = os.getenv("CAPITAL_PASSWORD")
BASE_URL = os.getenv("CAPITAL_BASE_URL")

client = CapitalClient(API_KEY, LOGIN, PASS, BASE_URL)
positions = client.get_positions()
print("Raw Positions Data:")
import json
print(json.dumps(positions, indent=2))
