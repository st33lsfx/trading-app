import requests
import json
import time

class CapitalClient:
    def __init__(self, api_key, login, password, base_url="https://demo-api-capital.backend-capital.com", timeout=10):
        self.api_key = api_key
        self.login = login
        self.password = password
        self.base_url = base_url
        self.timeout = timeout  # Request timeout in seconds
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
                response = requests.post(endpoint, headers=headers, json=data, timeout=self.timeout)
                
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
        
        # Add timeout if not already specified
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        
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
        except requests.exceptions.Timeout as e:
            print(f"❌ Capital.com API Timeout ({self.timeout}s): {method} {endpoint}")
            print(f"   Error details: {str(e)}")
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Capital.com Connection Error: {method} {endpoint}")
            print(f"   Error details: {str(e)}")
            print(f"   Possible causes: DNS failure, network unreachable, or API server down")
            return None
        except requests.exceptions.SSLError as e:
            print(f"❌ Capital.com SSL/TLS Error: {method} {endpoint}")
            print(f"   Error details: {str(e)}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Capital.com Request Error: {method} {endpoint}")
            print(f"   Error details: {str(e)}")
            return None
        except Exception as e:
            print(f"❌ Capital.com Unexpected Error: {method} {endpoint}")
            print(f"   Error type: {type(e).__name__}")
            print(f"   Error details: {str(e)}")
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
                'margin_factor': margin_factor,
                'market_status': snapshot.get('marketStatus', 'UNKNOWN')
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

    def _detect_asset_class(self, epic):
        """Detect asset class from epic name for SL/TP validation."""
        epic_upper = epic.upper()
        crypto_tokens = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOT",
                         "DOGE", "AVAX", "LINK", "MATIC", "LTC", "UNI", "ATOM"]
        for token in crypto_tokens:
            if token in epic_upper:
                return "crypto"
        # Forex: 6-letter pairs like EURUSD, GBPJPY
        forex_ccy = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "USD"]
        if len(epic_upper) == 6 and any(c in epic_upper for c in forex_ccy):
            return "forex"
        return "default"

    def place_market_order(self, epic, size, direction="BUY", stop_loss=None, take_profit=None, trailing_stop=False):
        """Place a market order (deal) with optional SL/TP.

        Capital.com API accepts either:
        - stopLevel/profitLevel: absolute price levels
        - stopDistance/profitDistance: distance in points from entry

        We use absolute levels (stopLevel, profitLevel).

        v3.1: Asset-class-aware minimum SL distances:
        - Crypto: min 1.5% SL (survives noise)
        - Forex: min 0.4% SL (~40+ pips on majors)
        - Default: min 0.8% SL
        """
        endpoint = f"{self.base_url}/api/v1/positions"
        data = {
            "epic": epic,
            "direction": direction,
            "size": size,
            "guaranteedStop": False,
            "trailingStop": trailing_stop
        }

        # Asset-class-aware minimum SL/TP distances (v5.0: match elite_strategy.py)
        asset_class = self._detect_asset_class(epic)
        MIN_SL_PCT = {
            "crypto": 0.025,   # v5.0: Min 2.5% SL — match strategy (was 2.0%)
            "forex": 0.008,    # v5.0: Min 0.8% SL — match strategy (was 0.6%)
            "default": 0.012,  # v5.0: Min 1.2% SL (was 1.0%)
        }
        MIN_RR = 1.3  # v5.0: Lower R:R to 1.3 (was 1.5) — allow wider SLs with more trade opportunities

        # Get current price to validate SL/TP direction
        try:
            prices = self.get_prices(epic)
            snapshot = prices.get('snapshot', {})
            current_bid = snapshot.get('bid', 0)
            current_offer = snapshot.get('offer', 0)
            entry_price = current_offer if direction == "BUY" else current_bid

            # R:R Logic Variables
            actual_sl_distance = 0

            if stop_loss and entry_price > 0:
                # Minimum SL distance based on asset class
                min_sl_distance = entry_price * MIN_SL_PCT.get(asset_class, 0.008)
                target_sl = stop_loss

                # Direction Check
                if direction == "BUY":
                    if target_sl >= entry_price: target_sl = entry_price - min_sl_distance
                else:
                     if target_sl <= entry_price: target_sl = entry_price + min_sl_distance

                # Minimum Distance Check
                current_dist = abs(entry_price - target_sl)
                if current_dist < min_sl_distance:
                    print(f"⚠️ SL too tight for {asset_class} ({current_dist:.5f}), widening to {min_sl_distance:.5f}")
                    current_dist = min_sl_distance
                    if direction == "BUY": target_sl = entry_price - min_sl_distance
                    else: target_sl = entry_price + min_sl_distance

                stop_loss = target_sl
                actual_sl_distance = current_dist
                data["stopLevel"] = round(stop_loss, 5)

            if take_profit and entry_price > 0 and actual_sl_distance > 0:
                # Calculate required TP based on Actual SL and MIN R:R
                min_tp_distance = actual_sl_distance * MIN_RR
                current_tp_dist = abs(entry_price - take_profit)

                if current_tp_dist < min_tp_distance:
                    print(f"⚠️ TP too close ({current_tp_dist:.5f}), pushing to {min_tp_distance:.5f} (R:R {MIN_RR})")
                    if direction == "BUY":
                        take_profit = entry_price + min_tp_distance
                    else:
                        take_profit = entry_price - min_tp_distance

                data["profitLevel"] = round(take_profit, 5)

        except Exception as e:
            # If price fetch fails, still try to place order with given levels
            if stop_loss:
                data["stopLevel"] = round(stop_loss, 5)
            if take_profit:
                data["profitLevel"] = round(take_profit, 5)

        # Retry logic — API občas neodpoví na první pokus
        last_error = None
        print(f"📍 Placing order: {epic} | {direction} | Size: {size} | SL: {data.get('stopLevel', 'None')} | TP: {data.get('profitLevel', 'None')}")
        
        for attempt in range(3):
            response = self._safe_request("POST", endpoint, json=data)
            if response:
                try:
                    result = response.json()
                except Exception as json_err:
                    last_error = f"Invalid JSON response (status {response.status_code})"
                    print(f"⚠️ Attempt {attempt+1}/3: {last_error}")
                    print(f"   Response text: {response.text[:200]}...")
                    time.sleep(1)
                    continue
                # Check for errors
                if 'errorCode' in result:
                    error_code = result.get('errorCode', 'UNKNOWN')
                    error_msg = result.get('errorMessage', error_code)
                    # Certain errors are not retryable
                    if error_code in ('INSUFFICIENT_FUNDS', 'MARKET_CLOSED', 'MARKET_NOT_FOUND',
                                      'REJECT_CFD_ORDER_ON_SPREADBET_ACCOUNT'):
                        raise Exception(f"Order rejected: {error_code} — {error_msg}")
                    # Retryable errors
                    last_error = f"Order error: {error_code} — {error_msg}"
                    print(f"⚠️ Attempt {attempt+1}/3: {last_error}")
                    time.sleep(2 ** attempt)
                    continue
                # Success!
                print(f"✅ Order placed successfully on attempt {attempt+1}")
                return result
            else:
                last_error = "No response from API (check error logs above for details)"
                print(f"⚠️ Attempt {attempt+1}/3: API request returned None, retrying in {2 ** attempt}s...")
                time.sleep(2 ** attempt)
                # Re-authenticate in case session expired
                if attempt == 1:
                    print("🔄 Re-authenticating in case of session expiry...")
                    self.authenticate()
        
        # All retries exhausted
        print(f"❌ Order FAILED after 3 attempts")
        print(f"   Epic: {epic}, Direction: {direction}, Size: {size}")
        print(f"   Final error: {last_error}")
        raise Exception(f"Order failed after 3 attempts: {last_error}")

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
    
    def close_position(self, deal_id):
        """Úplně zavři pozici."""
        endpoint = f"{self.base_url}/api/v1/positions/{deal_id}"
        response = self._safe_request("DELETE", endpoint)
        if response:
            return response.json()
        return None
    
    def reduce_position(self, deal_id, reduce_size):
        """
        Částečně zavři pozici (partial profit taking).
        
        Args:
            deal_id: ID pozice
            reduce_size: Kolik jednotek zavřít (kladné číslo)
        
        Returns:
            dict s výsledkem nebo None
        """
        # Capital.com API: Pro partial close musíme otevřít opačnou pozici
        # Alternativně některé API to podporují přes PUT s novým size
        endpoint = f"{self.base_url}/api/v1/positions/{deal_id}"
        
        # Nejdřív získej info o pozici
        try:
            positions = self.get_positions()
            target_pos = None
            for p in positions:
                pos_data = p.get('position', {})
                if pos_data.get('dealId') == deal_id:
                    target_pos = p
                    break
            
            if not target_pos:
                print(f"Position {deal_id} not found")
                return None
            
            market = target_pos.get('market', {})
            pos_data = target_pos.get('position', {})
            epic = market.get('epic')
            direction = pos_data.get('direction')
            current_size = pos_data.get('size', 0)
            
            if reduce_size >= current_size:
                # Zavři celou pozici
                return self.close_position(deal_id)
            
            # Otevři opačnou pozici pro partial close
            opposite_dir = "SELL" if direction == "BUY" else "BUY"
            result = self.place_market_order(epic, reduce_size, direction=opposite_dir)
            
            print(f"✅ Partial close: {reduce_size} of {epic} ({opposite_dir})")
            return result
            
        except Exception as e:
            print(f"❌ Reduce position error: {e}")
            return None

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
