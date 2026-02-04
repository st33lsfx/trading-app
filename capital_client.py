import requests
import json
import time

class CapitalClient:
    def __init__(self, api_key, login, password, base_url="https://demo-api-capital.backend-capital.com"):
        self.api_key = api_key
        self.login = login
        self.password = password
        self.base_url = base_url
        self.cst = None
        self.x_security_token = None
        self._last_request_time = 0
        self._min_request_interval = 0.5  # 500ms between requests to avoid rate limiting
        self.authenticate()

    def _rate_limit(self):
        """Ensure minimum interval between API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def authenticate(self, retry_count=3):
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
        
        for attempt in range(retry_count):
            try:
                self._rate_limit()
                response = requests.post(endpoint, headers=headers, json=data)
                
                # Handle rate limiting
                if response.status_code == 429:
                    wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                    print(f"Capital.com: Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                response.raise_for_status()
                
                # Capture security tokens from headers
                self.cst = response.headers.get("CST")
                self.x_security_token = response.headers.get("X-SECURITY-TOKEN")
                print("Capital.com: Authenticated successfully.")
                return
                
            except Exception as e:
                if attempt < retry_count - 1:
                    print(f"Capital.com Auth attempt {attempt + 1} failed: {e}")
                    time.sleep(1)
                else:
                    print(f"Capital.com Auth Failed after {retry_count} attempts: {e}")
                    if 'response' in locals():
                        print(response.text)

    def _get_headers(self):
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self.cst,
            "X-SECURITY-TOKEN": self.x_security_token,
            "Content-Type": "application/json"
        }

    def _safe_request(self, method, endpoint, **kwargs):
        """Make a rate-limited request with error handling."""
        self._rate_limit()
        try:
            response = requests.request(method, endpoint, headers=self._get_headers(), **kwargs)
            
            # Handle rate limiting
            if response.status_code == 429:
                print("Capital.com: Rate limited, waiting 2s...")
                time.sleep(2)
                self._rate_limit()
                response = requests.request(method, endpoint, headers=self._get_headers(), **kwargs)
            
            # Re-authenticate if session expired
            if response.status_code == 401:
                print("Capital.com: Session expired, re-authenticating...")
                self.authenticate()
                response = requests.request(method, endpoint, headers=self._get_headers(), **kwargs)
            
            return response
        except Exception as e:
            print(f"Capital.com API Error: {e}")
            return None

    def get_account_info(self):
        """Get account details."""
        endpoint = f"{self.base_url}/api/v1/accounts"
        response = self._safe_request("GET", endpoint)
        if response:
            return response.json()
        return {"accounts": []}

    def get_positions(self):
        """Get open positions."""
        endpoint = f"{self.base_url}/api/v1/positions"
        response = self._safe_request("GET", endpoint)
        if response:
            data = response.json()
            # Normalize to list
            positions = data.get('positions', [])
            if isinstance(positions, list):
                return positions
        return []

    def get_instruments(self):
        """Fetch instruments (Market Navigation)."""
        endpoint = f"{self.base_url}/api/v1/marketnavigation"
        response = self._safe_request("GET", endpoint)
        if response:
            return response.json()
        return {}

    def search_markets(self, query):
        """Search for markets by name."""
        endpoint = f"{self.base_url}/api/v1/markets?searchTerm={query}"
        response = self._safe_request("GET", endpoint)
        if response:
            return response.json()
        return {"markets": []}

    def get_instrument_info(self, epic):
        """Get instrument details including min/max size."""
        try:
            info = self.get_prices(epic)
            rules = info.get('dealingRules', {})
            snapshot = info.get('snapshot', {})
            margin_factor = rules.get('marginFactorValue', 0.05) or 0.05
            return {
                'min_size': rules.get('minDealSize', {}).get('value', 0.1),
                'max_size': rules.get('maxDealSize', {}).get('value', 100000),
                'lot_size': info.get('instrument', {}).get('lotSize', 1),
                'bid': snapshot.get('bid', 0),
                'offer': snapshot.get('offer', 0),
                'margin_factor': margin_factor
            }
        except:
            return {'min_size': 0.1, 'max_size': 100000, 'lot_size': 1, 'margin_factor': 0.05}
    
    def can_afford_instrument(self, epic, trade_amount):
        """Quick check if instrument is affordable with given trade amount."""
        try:
            info = self.get_instrument_info(epic)
            min_size = info.get('min_size', 0.1)
            bid = info.get('bid', 0)
            margin_factor = info.get('margin_factor', 0.05)
            
            if bid <= 0:
                return True  # Can't determine, let it try
            
            # Calculate minimum margin required
            min_margin = min_size * bid * margin_factor
            return min_margin <= trade_amount
        except:
            return True  # Can't determine, let it try

    def place_market_order(self, epic, size, direction="BUY", stop_loss=None, take_profit=None, trailing_stop=False):
        """Place a market order (deal) with optional SL/TP.
        
        Capital.com API accepts either:
        - stopLevel/profitLevel: absolute price levels
        - stopDistance/profitDistance: distance in points from entry
        
        We use absolute levels (stopLevel, profitLevel).
        """
        endpoint = f"{self.base_url}/api/v1/positions"
        data = {
            "epic": epic,
            "direction": direction,
            "size": size,
            "guaranteedStop": False,
            "trailingStop": trailing_stop
        }

        # Get current price to validate SL/TP direction
        try:
            prices = self.get_prices(epic)
            snapshot = prices.get('snapshot', {})
            current_bid = snapshot.get('bid', 0)
            current_offer = snapshot.get('offer', 0)
            entry_price = current_offer if direction == "BUY" else current_bid
            
            if stop_loss and entry_price > 0:
                # Validate SL is on correct side
                if direction == "BUY" and stop_loss >= entry_price:
                    # SL must be BELOW entry for BUY - fix it
                    stop_loss = entry_price * 0.995  # 0.5% below
                elif direction == "SELL" and stop_loss <= entry_price:
                    # SL must be ABOVE entry for SELL - fix it
                    stop_loss = entry_price * 1.005  # 0.5% above
                
                # Ensure minimum distance (at least 0.5% from entry)
                min_sl_distance = entry_price * 0.005
                actual_sl_distance = abs(entry_price - stop_loss)
                
                # If SL is too tight, widen it
                if actual_sl_distance < min_sl_distance:
                    if direction == "BUY":
                        stop_loss = entry_price - min_sl_distance
                    else:
                        stop_loss = entry_price + min_sl_distance
                    actual_sl_distance = min_sl_distance
                        
                data["stopLevel"] = round(stop_loss, 5)

            if take_profit and entry_price > 0:
                # Calculate implied R:R based on FINAL Stop Loss
                # Original TP distance?
                # We should ensure TP is at least 1.5x Risk (Dynamic Adjustment)
                desired_tp_distance = actual_sl_distance * 1.5
                
                if direction == "BUY":
                    # Current TP distance
                    current_tp_dist = take_profit - entry_price
                    # If current TP is too close relative to new SL, push it out
                    if current_tp_dist < desired_tp_distance:
                        take_profit = entry_price + desired_tp_distance
                    
                    # Basic validation (must be above entry)
                    if take_profit <= entry_price:
                        take_profit = entry_price * 1.01
                        
                elif direction == "SELL":
                     current_tp_dist = entry_price - take_profit
                     if current_tp_dist < desired_tp_distance:
                         take_profit = entry_price - desired_tp_distance
                     
                     if take_profit >= entry_price:
                         take_profit = entry_price * 0.99
                    
                data["profitLevel"] = round(take_profit, 5)
                
        except Exception as e:
            # If price fetch fails, still try to place order with given levels
            if stop_loss:
                data["stopLevel"] = round(stop_loss, 5)
            if take_profit:
                data["profitLevel"] = round(take_profit, 5)

        response = self._safe_request("POST", endpoint, json=data)
        if response:
            result = response.json()
            # Check for errors and raise exception
            if 'errorCode' in result:
                raise Exception(f"Order rejected: {result.get('errorCode')}")
            return result
        raise Exception("Order failed: No response from API")

    def update_position(self, deal_id, stop_level=None, profit_level=None):
        """Update SL/TP for an existing position."""
        endpoint = f"{self.base_url}/api/v1/positions/{deal_id}"
        data = {}
        if stop_level is not None:
            data["stopLevel"] = round(stop_level, 5)
        if profit_level is not None:
            data["profitLevel"] = round(profit_level, 5)
            
        if not data: return False
        
        response = self._safe_request("PUT", endpoint, json=data)
        if response:
            return True
        return False

    def get_prices(self, epic):
        """Get live price for an epic."""
        endpoint = f"{self.base_url}/api/v1/markets/{epic}"
        response = self._safe_request("GET", endpoint)
        if response:
            return response.json()
        return {}

    def get_history(self, last_hours=24):
        """Fetch trade history (transactions) for the last N hours."""
        to_time = int(time.time() * 1000)
        from_time = to_time - (last_hours * 3600 * 1000)
        return self.get_history_range(from_time, to_time)

    def get_history_range(self, from_time_ms, to_time_ms):
        """Fetch transactions between two timestamps (ms)."""
        endpoint = f"{self.base_url}/api/v1/history/transactions?from={from_time_ms}&to={to_time_ms}"
        response = self._safe_request("GET", endpoint)
        if response:
            try:
                return response.json().get('transactions', [])
            except:
                pass
        return []

    def get_navigation_node(self, node_id):
        """Fetch details/children of a specific navigation node."""
        endpoint = f"{self.base_url}/api/v1/marketnavigation/{node_id}"
        response = self._safe_request("GET", endpoint)
        if response:
            return response.json()
        return {}

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
