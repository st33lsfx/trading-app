import requests
import json

class CapitalClient:
    def __init__(self, api_key, login, password, base_url="https://demo-api-capital.backend-capital.com"):
        self.api_key = api_key
        self.login = login
        self.password = password
        self.base_url = base_url
        self.cst = None
        self.x_security_token = None
        self.authenticate()

    def authenticate(self):
        """Authenticate and get session tokens (CST and X-SECURITY-TOKEN)."""
        endpoint = f"{self.base_url}/api/v1/session"
        headers = {
            "X-CAP-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        data = {
            "identifier": self.login,
            "password": self.password,
            "encryptedPassword": False
        }
        
        try:
            response = requests.post(endpoint, headers=headers, json=data)
            response.raise_for_status()
            
            # Capture security tokens from headers
            self.cst = response.headers.get("CST")
            self.x_security_token = response.headers.get("X-SECURITY-TOKEN")
            print("Capital.com: Authenticated successfully.")
        except Exception as e:
            print(f"Capital.com Auth Failed: {e}")
            if 'response' in locals():
                print(response.text)

    def _get_headers(self):
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self.cst,
            "X-SECURITY-TOKEN": self.x_security_token,
            "Content-Type": "application/json"
        }

    def get_account_info(self):
        """Get account details."""
        endpoint = f"{self.base_url}/api/v1/accounts"
        response = requests.get(endpoint, headers=self._get_headers())
        return response.json()

    def get_positions(self):
        """Get open positions."""
        endpoint = f"{self.base_url}/api/v1/positions"
        response = requests.get(endpoint, headers=self._get_headers())
        data = response.json()
        # Normalize to list
        return data.get('positions', [])

    def get_instruments(self):
        """Fetch instruments (Market Navigation or specific search).
        Capital has a complex hierarchy. We'll search for 'top' or 'all' equivalent.
        For simplicity in bot, we might fetch a snapshot or search.
        Endpoint: /api/v1/markets
        """
        # Fetching all markets can be huge. Let's try to fetch a specific node or search.
        # For a bot, maybe we search for specific tickers?
        # Or we can iterate top level nodes.
        # Let's try fetching details for a known watchlist later.
        # For now, let's just get top level markets to verify connection.
        endpoint = f"{self.base_url}/api/v1/marketnavigation"
        response = requests.get(endpoint, headers=self._get_headers())
        return response.json()

    def search_markets(self, query):
        """Search for markets by name."""
        endpoint = f"{self.base_url}/api/v1/markets?searchTerm={query}"
        response = requests.get(endpoint, headers=self._get_headers())
        return response.json()

    def place_market_order(self, epic, size, direction="BUY", stop_loss=None, take_profit=None):
        """Place a market order (deal) with optional SL/TP."""
        endpoint = f"{self.base_url}/api/v1/positions"
        data = {
            "epic": epic,
            "direction": direction,
            "size": size,
            "guaranteedStop": False,
            "trailingStop": False
        }
        
        if stop_loss:
            data["stopLevel"] = stop_loss
            
        if take_profit:
            data["profitLevel"] = take_profit
            
        response = requests.post(endpoint, headers=self._get_headers(), json=data)
        return response.json()

    def get_prices(self, epic):
        """Get live price for an epic."""
        endpoint = f"{self.base_url}/api/v1/markets/{epic}"
        response = requests.get(endpoint, headers=self._get_headers())
        return response.json()

    def get_navigation_node(self, node_id):
        """Fetch details/children of a specific navigation node."""
        endpoint = f"{self.base_url}/api/v1/marketnavigation/{node_id}"
        response = requests.get(endpoint, headers=self._get_headers())
        return response.json()

    def get_all_markets_from_node(self, node_id):
        """Recursively fetch all markets under a node."""
        markets = []
        try:
            data = self.get_navigation_node(node_id)
            
            # Check for sub-nodes
            if 'nodes' in data:
                for sub_node in data['nodes']:
                    # Recurse
                    markets.extend(self.get_all_markets_from_node(sub_node['id']))
            
            # Check for markets in this node
            if 'markets' in data:
                for m in data['markets']:
                    markets.append(m)
                    
        except Exception as e:
            print(f"Error traversing node {node_id}: {e}")
            
        return markets
