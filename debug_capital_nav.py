import os
import json
from dotenv import load_dotenv
from capital_client import CapitalClient

load_dotenv()
API_KEY = os.getenv("CAPITAL_API_KEY")
LOGIN = os.getenv("CAPITAL_LOGIN")
PASS = os.getenv("CAPITAL_PASSWORD")
BASE_URL = os.getenv("CAPITAL_BASE_URL")

try:
    client = CapitalClient(API_KEY, LOGIN, PASS, BASE_URL)
    nav = client.get_instruments() # This calls marketnavigation
    
    print("Top Level Nodes:")
    if 'nodes' in nav:
        for node in nav['nodes']:
            print(f"- {node.get('name')} (ID: {node.get('id')})")
            
            # Print first level children if specific categories
            if node.get('name') in ['Forex', 'Commodities', 'Indices', 'Cryptocurrencies']:
                 print(f"  FAILED TO EXPAND {node.get('name')}") 
                 # Usually marketnavigation returns full tree or just top level?
                 # If just top level, we might need to query specific node.
                 
    # Let's save it to inspect
    with open("nav_tree.json", "w") as f:
        json.dump(nav, f, indent=2)
    print("\nSaved full tree to nav_tree.json")
    
except Exception as e:
    print(e)
