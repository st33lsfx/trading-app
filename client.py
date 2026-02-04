import requests
import json

class Trading212Client:
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        # Validated: Direct Authorization header works for this key
        self.headers = {
            "Authorization": self.api_key
        }

    def get_account_cash(self):
        """Fetch account cash balance."""
        endpoint = f"{self.base_url}/equity/account/cash"
        response = requests.get(endpoint, headers=self.headers)
        return response.json()

    def get_account_summary(self):
        """Fetch account summary."""
        endpoint = f"{self.base_url}/equity/account/summary"
        response = requests.get(endpoint, headers=self.headers)
        return response.json()

    def get_open_orders(self):
        """Fetch all open orders."""
        endpoint = f"{self.base_url}/equity/orders"
        response = requests.get(endpoint, headers=self.headers)
        return response.json()

    def get_positions(self):
        """Fetch all open positions."""
        endpoint = f"{self.base_url}/equity/positions"
        response = requests.get(endpoint, headers=self.headers)
        return response.json()

    def get_instruments(self):
        """Fetch all tradable instruments."""
        endpoint = f"{self.base_url}/equity/metadata/instruments"
        response = requests.get(endpoint, headers=self.headers)
        return response.json()

    def get_exchanges(self):
        """Fetch all exchange metadata (schedules)."""
        endpoint = f"{self.base_url}/equity/metadata/exchanges"
        response = requests.get(endpoint, headers=self.headers)
        return response.json()

    def place_market_order(self, ticker, quantity):
        """Place a market order."""
        endpoint = f"{self.base_url}/equity/orders/market"
        # Negative quantity for sell is handled by the API convention, 
        # but usually passed as positive in JSON body with 'quantity' field? 
        # Docs say: "Selling Orders: To execute a sell order, you must provide a negative value for the quantity parameter"
        # So we just pass the signed float.
        data = {
            "ticker": ticker,
            "quantity": quantity
        }
        response = requests.post(endpoint, headers=self.headers, json=data)
        return response.json()
        
    def place_limit_order(self, ticker, quantity, limit_price, time_validity="DAY"):
        """Place a limit order."""
        endpoint = f"{self.base_url}/equity/orders/limit"
        data = {
            "ticker": ticker,
            "quantity": quantity,
            "limitPrice": limit_price,
            "timeValidity": time_validity
        }
        response = requests.post(endpoint, headers=self.headers, json=data)
        return response.json()

    def place_stop_order(self, ticker, quantity, stop_price, time_validity="DAY"):
        """Place a stop order (Trigger market order when price hit)."""
        endpoint = f"{self.base_url}/equity/orders/stop"
        data = {
            "ticker": ticker,
            "quantity": quantity,
            "stopPrice": stop_price,
            "timeValidity": time_validity
        }
        response = requests.post(endpoint, headers=self.headers, json=data)
        return response.json()
