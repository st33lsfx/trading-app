import time
import os
import random
import threading
from datetime import datetime, date
from dotenv import load_dotenv
from client import Trading212Client
from strategy import Strategy
from mean_reversion_strategy import MeanReversionStrategy
from market_utils import is_market_open, map_ticker_to_yf

load_dotenv()

# Global Configuration - HIGH VOLUME MODE (70% WR, 12 tr/den)
MAX_POSITIONS = 5          # Více pozic pro více obchodů
TRADE_AMOUNT_CZK = 100     # ~$4 per trade
SL_PCT = 0.01              # 1% SL
TP_PCT = 0.012             # 1.2% TP (R:R 1.2:1)
MAX_SCAN_PER_CYCLE = 50    # Scan více assetů
INTERVAL = "5m"
PERIOD = "5d"

from capital_client import CapitalClient

class TradingBot:
    def __init__(self, api_key, base_url, broker="t212", cap_login=None, cap_pass=None):
        self.broker = broker
        self.api_key = api_key
        self.trade_amount = 4.0  # Default for small account (~$4 per trade)
        self.small_account_mode = True  # Enable for accounts under $200
        # Check broker type
        if self.broker == "capital":
            self.client = CapitalClient(api_key, cap_login, cap_pass, base_url)
        else:
            self.client = Trading212Client(api_key, base_url)
            
        self.is_running = False
        self.log_messages = []
        self.instruments = []
        self.open_instruments = []
        self._thread = None
        self.max_positions = MAX_POSITIONS  # Can be changed from dashboard

        # === STRATEGY SELECTION ===
        # "momentum" = původní strategie s RSI, ADX, EMA
        # "mean_reversion" = Bollinger Bands mean reversion (DOPORUČENO)
        self.strategy_type = "mean_reversion"  # DEFAULT: Mean Reversion
        self.mean_reversion = MeanReversionStrategy()

        # UI & Strategy State (Initialized here for immediate access)
        self.scan_results = []
        self.last_trade_times = {}
        
        # =====================================================
        # HIGH VOLUME + HIGH WR - OVĚŘENO BACKTESTEM (únor 2026)
        # =====================================================
        # Výsledky: 70% WR, 12 obchodů/den, 268 obchodů/měsíc
        # Return: 23.6% bez páky → 236% s pákou 1:10
        # 2000 Kč → 6710 Kč měsíčně!
        self.strategy_config = {
            "rsi_buy": 55,
            "rsi_oversold": 40,
            "rsi_sell": 45,
            "rsi_overbought": 60,
            "adx_min": 12,           # Nízký = hodně obchodů
            "risk_reward": 1.2,      # Rychlý TP = vyšší WR
            "atr_sl_mult": 1.0,
            "max_risk_pct": 0.02,    # 2% risk per trade
            "require_volume": False,
            "require_session": False,
            "enable_shorts": True,
        }
        
        # =====================================================
        # BLACKLIST - ZTRÁTOVÉ (aktualizováno únor 2026)
        # =====================================================
        self.ticker_blacklist = [
            # Ztrátové v backtestu s aktuální konfigurací
            "BTCUSD", "BTC-USD", "BTC",    # Nestabilní
            "EURUSD", "EURUSD=X",          # Ztrátový
            "LTCUSD", "LTC-USD",           # PF < 1
            "XRPUSD", "XRP-USD",           # PF < 1
            "Gold", "GC=F", "XAUUSD",      # Ztrátový
            "MSFT",                         # Break-even

            # Příliš drahé pro malý účet (JPY páry)
            "USDJPY", "USDJPY=X", "EURJPY", "EURJPY=X",
            "GBPJPY", "GBPJPY=X", "AUDJPY", "AUDJPY=X",
            "XAGUSD", "SI=F", "Silver",
        ]
        # GBPUSD ODSTRANĚN z blacklistu - nyní profitabilní (PF 1.43)
        
        # =====================================================
        # ROZŠÍŘENÝ SEZNAM ASSETŮ - 30+ instrumentů
        # =====================================================
        # Pro 2000 Kč kapitál potřebujeme více assetů = více signálů
        # Mean Reversion strategy: ~10 signálů/den na asset
        self.priority_tickers = [
            # === CRYPTO - Nejvíc volatilní, nejvíc signálů ===
            {"epic": "ETHUSD", "yf": "ETH-USD", "name": "Ethereum", "pf": 1.83, "wr": 77, "cat": "Crypto"},
            {"epic": "SOLUSD", "yf": "SOL-USD", "name": "Solana", "pf": 1.36, "wr": 58, "cat": "Crypto"},
            {"epic": "AVAXUSD", "yf": "AVAX-USD", "name": "Avalanche", "pf": 1.52, "wr": 73, "cat": "Crypto"},
            {"epic": "ADAUSD", "yf": "ADA-USD", "name": "Cardano", "pf": 1.16, "wr": 72, "cat": "Crypto"},
            {"epic": "DOTUSD", "yf": "DOT-USD", "name": "Polkadot", "pf": 1.20, "wr": 65, "cat": "Crypto"},
            {"epic": "LINKUSD", "yf": "LINK-USD", "name": "Chainlink", "pf": 1.15, "wr": 60, "cat": "Crypto"},
            {"epic": "MATICUSD", "yf": "MATIC-USD", "name": "Polygon", "pf": 1.10, "wr": 58, "cat": "Crypto"},
            {"epic": "ATOMUSD", "yf": "ATOM-USD", "name": "Cosmos", "pf": 1.12, "wr": 55, "cat": "Crypto"},
            {"epic": "NEARUSD", "yf": "NEAR-USD", "name": "NEAR", "pf": 1.08, "wr": 54, "cat": "Crypto"},
            {"epic": "ALGOUSD", "yf": "ALGO-USD", "name": "Algorand", "pf": 1.05, "wr": 52, "cat": "Crypto"},

            # === FOREX - Major a Minor páry ===
            {"epic": "GBPUSD", "yf": "GBPUSD=X", "name": "GBP/USD", "pf": 1.43, "wr": 61, "cat": "Forex"},
            {"epic": "EURUSD", "yf": "EURUSD=X", "name": "EUR/USD", "pf": 1.04, "wr": 58, "cat": "Forex"},
            {"epic": "AUDUSD", "yf": "AUDUSD=X", "name": "AUD/USD", "pf": 1.17, "wr": 61, "cat": "Forex"},
            {"epic": "NZDUSD", "yf": "NZDUSD=X", "name": "NZD/USD", "pf": 1.43, "wr": 56, "cat": "Forex"},
            {"epic": "USDCAD", "yf": "USDCAD=X", "name": "USD/CAD", "pf": 1.10, "wr": 55, "cat": "Forex"},
            {"epic": "USDCHF", "yf": "USDCHF=X", "name": "USD/CHF", "pf": 1.08, "wr": 54, "cat": "Forex"},
            {"epic": "EURGBP", "yf": "EURGBP=X", "name": "EUR/GBP", "pf": 1.12, "wr": 56, "cat": "Forex"},
            {"epic": "EURAUD", "yf": "EURAUD=X", "name": "EUR/AUD", "pf": 1.15, "wr": 58, "cat": "Forex"},
            {"epic": "GBPAUD", "yf": "GBPAUD=X", "name": "GBP/AUD", "pf": 1.20, "wr": 60, "cat": "Forex"},
            {"epic": "AUDNZD", "yf": "AUDNZD=X", "name": "AUD/NZD", "pf": 1.08, "wr": 54, "cat": "Forex"},

            # === US STOCKS - Volatilní tech akcie ===
            {"epic": "AMD", "yf": "AMD", "name": "AMD", "pf": 12.44, "wr": 91, "cat": "US Stocks"},
            {"epic": "NVDA", "yf": "NVDA", "name": "NVIDIA", "pf": 1.30, "wr": 60, "cat": "US Stocks"},
            {"epic": "TSLA", "yf": "TSLA", "name": "Tesla", "pf": 1.25, "wr": 58, "cat": "US Stocks"},
            {"epic": "AAPL", "yf": "AAPL", "name": "Apple", "pf": 1.15, "wr": 55, "cat": "US Stocks"},
            {"epic": "MSFT", "yf": "MSFT", "name": "Microsoft", "pf": 1.10, "wr": 54, "cat": "US Stocks"},
            {"epic": "GOOGL", "yf": "GOOGL", "name": "Google", "pf": 1.12, "wr": 55, "cat": "US Stocks"},
            {"epic": "META", "yf": "META", "name": "Meta", "pf": 1.18, "wr": 57, "cat": "US Stocks"},
            {"epic": "AMZN", "yf": "AMZN", "name": "Amazon", "pf": 1.08, "wr": 53, "cat": "US Stocks"},
            {"epic": "PLTR", "yf": "PLTR", "name": "Palantir", "pf": 1.20, "wr": 58, "cat": "US Stocks"},
            {"epic": "COIN", "yf": "COIN", "name": "Coinbase", "pf": 1.15, "wr": 56, "cat": "US Stocks"},
        ]

        # Celkem: 30 assetů = potenciálně 300+ signálů/den
        # =====================================================
        # AGGRESSIVE MODE - Cíl: 100% měsíčně (2000→4000 Kč)
        # =====================================================
        # Potřeba: ~4.5% denně = ~$3.50/den při $80 kapitálu
        # S pákou 1:20 = potřeba ~0.23% pohyb na obchod

        self.daily_pnl = 0.0
        self.daily_reset_date = date.today().isoformat()
        self.max_daily_loss = 8.0     # USD (~200 Kč) – max 10% denní ztráta
        self.daily_profit_target = 4.0 # USD (~100 Kč) – realistický denní cíl
        self.session_stopped_reason = None
        self._daily_pnl_lock = threading.Lock()

        # === HIGH VOLUME SETTINGS ===
        self.aggressive_mode = True

        # Position sizing
        self.margin_usage_pct = 0.40  # 40% marginu
        self.max_positions = 5        # Více pozic = více obchodů

        # Kelly Criterion - based on backtest (70% WR)
        self.kelly_win_rate = 0.70    # 70% WR z backtestu
        self.kelly_avg_win = 1.2      # R:R 1.2
        self.kelly_avg_loss = 1.0
        self.kelly_fraction = 0.4     # 40% Kelly

        # Correlation filter - povolit více pozic
        self.max_forex_positions = 2
        self.max_crypto_positions = 3  # Více crypto (nejvíc trades)
        self.max_stock_positions = 1

        # Drawdown protection
        self.max_drawdown_pct = 20.0  # 20% max drawdown
        self.initial_balance = None

        # Spread filter - přísnější
        self.max_spread_pct = 0.10    # Max 0.1% spread

        # Trade tracking
        self.session_trades = []
        self.wins = 0
        self.losses = 0

        # Compounding - zvyšuj trade_amount s profitem
        self.compound_profits = True
        self.base_capital = 80.0      # $80 = 2000 Kč

    def log(self, message):
        timestamp = time.strftime('%H:%M:%S')
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        self.log_messages.append(full_msg)
        if len(self.log_messages) > 100: self.log_messages.pop(0)

    def initialize_data(self):
        """Pre-fetch necessary data."""
        self.log(f"Initializing ({self.broker.upper()})...")
        
        # Init Cache for UI
        self.cached_account = {}
        self.cached_positions = []
        self.last_trade_times = {} # Reset Cooldowns on Start
        self.scan_results = [] # Reset Scanner Logs
        # strategy_config is preserved from __init__ (User edits)
        
        if self.broker == "t212":
            try:
                self.instruments = self.client.get_instruments()
                self.exchanges = self.client.get_exchanges()
                self.log(f"Loaded {len(self.instruments)} instruments (T212).")
            except Exception as e:
                self.log(f"T212 Init Error: {e}")

        if self.broker == "capital":
            # Ensure categories are set
            if not hasattr(self, 'market_categories'):
                self.market_categories = {
                    "Indices": [], "Forex": [], "Commodities": [], "Crypto": [], "US Stocks": []
                }
            
            # Default active categories (Indices disabled - poor backtest results)
            if not hasattr(self, 'active_categories'):
                self.active_categories = ["Forex", "Commodities", "Crypto", "US Stocks"]

            self.scan_all_markets()

    def update_cache(self):
        """Fetch account data for UI (Non-blocking for Dashboard)."""
        try:
            if self.broker == "capital":
                self.cached_account = self.client.get_account_info()
            else:
                self.cached_account = self.client.get_account_cash()
            self.cached_positions = self.client.get_positions()
        except: 
            pass

    def update_daily_pnl(self):
        """Refresh today's PnL from broker history; reset on new day."""
        today = date.today().isoformat()
        with self._daily_pnl_lock:
            if today != self.daily_reset_date:
                self.daily_reset_date = today
                self.daily_pnl = 0.0
                self.session_stopped_reason = None
            if self.broker != "capital":
                return
        try:
            from datetime import datetime as dt
            start_today_utc = int(dt.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
            to_ts = int(time.time() * 1000)
            trans = self.client.get_history_range(start_today_utc, to_ts) if hasattr(self.client, 'get_history_range') else []
            if not trans:
                trans = self.client.get_history(last_hours=48)
            trades = [t for t in (trans or []) if t.get('profitAndLoss') is not None and t.get('profitAndLoss') != 0]
            day_start_ms = start_today_utc
            today_trades = [t for t in trades if (t.get('date') or t.get('transactionDate') or 0) >= day_start_ms]
            total = sum(float(t.get('profitAndLoss', 0)) for t in today_trades)
            with self._daily_pnl_lock:
                self.daily_pnl = total
            if self.max_daily_loss and total <= -abs(self.max_daily_loss):
                self.session_stopped_reason = "daily_loss"
            elif self.daily_profit_target and total >= self.daily_profit_target:
                self.session_stopped_reason = "profit_target"
        except Exception as e:
            pass

    # === PROFESSIONAL FILTER METHODS ===

    def update_trade_amount_compound(self):
        """Automaticky zvyšuj trade_amount s rostoucím účtem (compounding)."""
        if not self.compound_profits:
            return

        try:
            acc = self.client.get_account_info()
            accounts = acc.get('accounts', [])
            if accounts:
                balance = accounts[0].get('balance', {}).get('balance', 0)
                available = accounts[0].get('balance', {}).get('available', 0)

                if balance > 0:
                    # Compound: trade_amount = base_pct * aktuální balance
                    # Pro agresivní režim: 5-10% účtu per trade
                    growth_factor = balance / self.base_capital

                    # Základní trade amount roste s účtem
                    new_trade_amount = min(
                        available * self.margin_usage_pct / self.max_positions,
                        balance * 0.10  # Max 10% účtu per trade
                    )

                    # Minimum $3, max $50 per trade
                    self.trade_amount = max(3.0, min(50.0, new_trade_amount))

                    if growth_factor > 1.1:  # Účet narostl o 10%+
                        self.log(f"📈 COMPOUND: Balance ${balance:.2f} (+{(growth_factor-1)*100:.0f}%), Trade amount: ${self.trade_amount:.2f}")
        except:
            pass

    def get_optimal_trade_size(self, epic, current_price):
        """Vypočítej optimální velikost pozice pro daný instrument."""
        try:
            # Získej info o instrumentu
            inst_info = self.client.get_instrument_info(epic)
            min_size = inst_info.get('min_size', 0.1)
            margin_factor = inst_info.get('margin_factor', 0.05)

            # Aktualizuj trade_amount podle compoundingu
            self.update_trade_amount_compound()

            # Vypočítej velikost
            if current_price > 0:
                # Kolik můžeme koupit za trade_amount
                raw_size = self.trade_amount / (current_price * margin_factor)

                # Zaokrouhli a ověř minimum
                size = max(min_size, round(raw_size, 3))

                return size, min_size, margin_factor

            return min_size, min_size, margin_factor
        except:
            return 0.1, 0.1, 0.05

    def calculate_kelly_size(self, base_amount):
        """Calculate position size using Kelly Criterion."""
        # Kelly formula: f* = (p*b - q) / b
        # where p=win_rate, q=1-p, b=avg_win/avg_loss
        p = self.kelly_win_rate
        q = 1 - p
        b = self.kelly_avg_win / self.kelly_avg_loss

        kelly_pct = (p * b - q) / b if b > 0 else 0
        kelly_pct = max(0, min(kelly_pct, 0.25))  # Cap at 25%

        # Use fraction of Kelly (conservative)
        adjusted_size = base_amount * (1 + kelly_pct * self.kelly_fraction)
        return round(adjusted_size, 2)

    def check_correlation_filter(self, epic, category):
        """Check if we already have too many positions in this category."""
        positions = self.client.get_positions()

        # Count positions by category
        forex_count = 0
        crypto_count = 0
        stock_count = 0

        for p in positions:
            market = p.get('market', {})
            inst_type = market.get('instrumentType', '')
            epic_name = market.get('epic', '')

            if inst_type == 'CURRENCIES' or 'USD' in epic_name and len(epic_name) == 6:
                forex_count += 1
            elif inst_type == 'CRYPTOCURRENCIES' or epic_name.endswith('USD') and len(epic_name) > 6:
                crypto_count += 1
            elif inst_type == 'SHARES':
                stock_count += 1

        # Check limits
        if category == "Forex" and forex_count >= self.max_forex_positions:
            return False, f"Max Forex positions ({self.max_forex_positions})"
        if category == "Crypto" and crypto_count >= self.max_crypto_positions:
            return False, f"Max Crypto positions ({self.max_crypto_positions})"
        if category == "US Stocks" and stock_count >= self.max_stock_positions:
            return False, f"Max Stock positions ({self.max_stock_positions})"

        return True, "OK"

    def check_spread_filter(self, epic):
        """Check if spread is acceptable for trading."""
        try:
            info = self.client.get_instrument_info(epic)
            bid = info.get('bid', 0)
            offer = info.get('offer', 0)

            if bid > 0 and offer > 0:
                spread_pct = ((offer - bid) / bid) * 100
                if spread_pct > self.max_spread_pct:
                    return False, f"Spread too high: {spread_pct:.3f}%"
            return True, "OK"
        except:
            return True, "OK"  # Allow if can't check

    def check_drawdown_protection(self):
        """Stop trading if account drawdown exceeds limit."""
        try:
            acc = self.client.get_account_info()
            accounts = acc.get('accounts', [])
            if accounts:
                balance = accounts[0].get('balance', {}).get('balance', 0)

                # Set initial balance on first check
                if self.initial_balance is None:
                    self.initial_balance = balance
                    return True, "OK"

                # Calculate drawdown
                if self.initial_balance > 0:
                    drawdown_pct = ((self.initial_balance - balance) / self.initial_balance) * 100
                    if drawdown_pct >= self.max_drawdown_pct:
                        return False, f"Drawdown protection: -{drawdown_pct:.1f}%"

            return True, "OK"
        except:
            return True, "OK"

    def get_category_for_epic(self, epic):
        """Determine category for an epic."""
        for cat, items in self.market_categories.items():
            for item in items:
                if item.get('epic') == epic:
                    return cat
        # Fallback detection
        if len(epic) == 6 and epic.isalpha():
            return "Forex"
        if epic.endswith('USD') and len(epic) > 6:
            return "Crypto"
        return "US Stocks"

    def set_active_categories(self, categories):
        """Update active scanning categories."""
        self.active_categories = categories
        self.log(f"Active Categories updated: {categories}")
        self.open_instruments = [] # Force refresh
        # Note: Current running cycle will finish with old list, next cycle will use new.

    def is_blacklisted(self, ticker):
        """Check if ticker is in blacklist (poor backtest results)."""
        if not hasattr(self, 'ticker_blacklist'):
            return False
        for bl in self.ticker_blacklist:
            if bl.upper() in ticker.upper():
                return True
        return False

    def scan_all_markets(self):
        """Dynamically fetch all markets from Capital.com."""
        self.log("Starting Dynamic Market Scan... (This may take a moment)")
        
        # Category IDs (from debug output)
        ids = {
            "Forex": "hierarchy_v1.forex",
            "Indices": "hierarchy_v1.indices_group",
            "Commodities": "hierarchy_v1.commodities_group",
            "Crypto": "hierarchy_v1.crypto_currencies_group",
        }
        
        # Manual List for US Stocks (Top Tech) - Scanning all shares is too heavy (thousands)
        self.market_categories["US Stocks"] = [
            {'epic': 'AAPL', 'yf': 'AAPL', 'name': 'Apple'},
            {'epic': 'TSLA', 'yf': 'TSLA', 'name': 'Tesla'},
            {'epic': 'NVDA', 'yf': 'NVDA', 'name': 'Nvidia'},
            {'epic': 'MSFT', 'yf': 'MSFT', 'name': 'Microsoft'},
            {'epic': 'AMZN', 'yf': 'AMZN', 'name': 'Amazon'},
        ]
        
        # Add priority tickers first (best backtest results)
        if hasattr(self, 'priority_tickers'):
            for pt in self.priority_tickers:
                # Determine category
                if "USD=X" in pt['yf'] or "JPY=X" in pt['yf']:
                    cat = "Forex"
                elif "-USD" in pt['yf']:
                    cat = "Crypto"
                elif "=F" in pt['yf']:
                    cat = "Commodities"
                else:
                    cat = "Forex"
                
                if cat in self.market_categories:
                    # Check if not already added
                    existing = [m['epic'] for m in self.market_categories[cat]]
                    if pt['epic'] not in existing:
                        self.market_categories[cat].insert(0, pt)  # Add at beginning (priority)
        
        for cat_name, node_id in ids.items():
            # Respect User Selection
            if hasattr(self, 'active_categories') and cat_name not in self.active_categories:
                continue

            try:
                markets = self.client.get_all_markets_from_node(node_id)
                self.log(f"Fetched {len(markets)} items for {cat_name}")
                
                # Convert to our internal format
                for m in markets:
                    epic = m.get('epic')
                    name = m.get('instrumentName')
                    yf_ticker = None
                    
                    # Skip blacklisted tickers
                    if self.is_blacklisted(epic):
                        continue
                    
                    # Auto-Mapper Logic
                    if cat_name == "Forex":
                        clean_epic = epic.replace("/", "").replace("-", "")
                        if len(clean_epic) == 6:
                             yf_ticker = f"{clean_epic}=X"
                             # Skip blacklisted forex pairs
                             if self.is_blacklisted(yf_ticker):
                                 continue
                        elif "CZK" in clean_epic:
                             yf_ticker = f"{clean_epic}=X"
                             
                    elif cat_name == "Crypto":
                        # Skip all blacklisted crypto
                        if self.is_blacklisted(epic):
                            continue
                        if "USD" in epic:
                             coin = epic.replace("USD", "")
                             yf_ticker = f"{coin}-USD"
                             if self.is_blacklisted(yf_ticker):
                                 continue
                    
                    elif cat_name == "Indices":
                        idx_map = {
                            "US500": "^GSPC", "USTEch100": "^NDX", "US30": "^DJI",
                            "DE40": "^GDAXI", "UK100": "^FTSE", "FR40": "^FCHI"
                        }
                        if epic in idx_map: yf_ticker = idx_map[epic]

                    elif cat_name == "Commodities":
                        # Skip Gold (blacklisted)
                        if self.is_blacklisted(epic):
                            continue
                        com_map = {
                            "Silver": "SI=F", "Oil": "CL=F", "NaturalGas": "NG=F"
                            # Gold removed - poor backtest results
                        }
                        if epic in com_map: yf_ticker = com_map[epic]
                    
                    if yf_ticker:
                        self.market_categories[cat_name].append({
                            'epic': epic,
                            'yf': yf_ticker,
                            'name': name
                        })
                        
            except Exception as e:
                self.log(f"Error scanning {cat_name}: {e}")
        
        # Log summary
        total = sum(len(v) for v in self.market_categories.values())
        self.log(f"Scan Complete. Total markets: {total} (Blacklisted excluded)")

    def get_open_markets(self):
        self.open_instruments = []
        priority_added = set()
        
        if self.broker == "t212":
            # Existing T212 Logic
            for instr in self.instruments:
                if instr['type'] not in ['STOCK', 'ETF']: continue
                yf_ticker = map_ticker_to_yf(instr['ticker'])
                if not yf_ticker: continue

                mock_exchange = {}
                if "_US_" in instr['ticker']: mock_exchange = {'name': 'US'}
                elif "_DE_" in instr['ticker']: mock_exchange = {'name': 'DEUTSCH'}
                elif "_UK_" in instr['ticker'] or instr.get('currencyCode') == 'GBP': mock_exchange = {'name': 'UK'}
                
                if is_market_open(mock_exchange):
                    self.open_instruments.append({
                        "t212": instr['ticker'], 
                        "yf": yf_ticker,
                        "currency": instr.get('currencyCode', 'USD')
                    })
        
        elif self.broker == "capital":
            # Small account mode: Use curated priority list filtered by active categories
            if getattr(self, 'small_account_mode', False) and hasattr(self, 'priority_tickers'):
                for pt in self.priority_tickers:
                    # Filter by active categories
                    pt_cat = pt.get('cat', 'Forex')
                    if pt_cat not in self.active_categories:
                        continue
                    # Skip blacklisted
                    if self.is_blacklisted(pt['yf']) or self.is_blacklisted(pt['epic']):
                        continue
                    self.open_instruments.append({
                        "epic": pt['epic'],
                        "yf": pt['yf'],
                        "currency": "USD",
                        "priority": True,
                        "expected_pf": pt.get('pf', 1.0)
                    })
                    priority_added.add(pt['epic'])
                
                cats_str = ", ".join(self.active_categories)
                self.log(f"💰 Small Account Mode: {len(self.open_instruments)} instruments ({cats_str})")
            else:
                # Normal mode: Add priority tickers first
                if hasattr(self, 'priority_tickers'):
                    for pt in self.priority_tickers:
                        if self.is_blacklisted(pt['yf']):
                            continue
                        self.open_instruments.append({
                            "epic": pt['epic'],
                            "yf": pt['yf'],
                            "currency": "USD",
                            "priority": True,
                            "expected_pf": pt.get('pf', 1.0)
                        })
                        priority_added.add(pt['epic'])
                
                # Then add other markets from categories
                for cat in self.active_categories:
                    if cat in self.market_categories:
                        for item in self.market_categories[cat]:
                            # Skip if already in priority list
                            if item['epic'] in priority_added:
                                continue
                            # Skip blacklisted
                            if self.is_blacklisted(item['yf']):
                                continue
                            self.open_instruments.append({
                                "epic": item['epic'],
                                "yf": item['yf'],
                                "currency": "USD",
                                "priority": False
                            })
        
        priority_count = len([x for x in self.open_instruments if x.get('priority')])
        self.log(f"Found {len(self.open_instruments)} markets ({priority_count} priority)")
        return self.open_instruments

    def process_instrument(self, ticker_data):
        # Unpack based on broker structure
        if self.broker == "t212":
            t212_ticker = ticker_data['t212']
            yf_ticker = ticker_data['yf']
            currency = ticker_data['currency']
            trade_func = self.client.place_market_order
        else:
            t212_ticker = ticker_data['epic'] # "epic" for Capital
            yf_ticker = ticker_data['yf']
            currency = ticker_data['currency']
            trade_func = self.client.place_market_order
        
        # Double-check blacklist
        if self.is_blacklisted(yf_ticker) or self.is_blacklisted(t212_ticker):
            return False
        
        # ========================================
        # COOLDOWN - Wait 30 min before trading same instrument again
        # ========================================
        COOLDOWN_SECONDS = 1800  # 30 minutes
        last_trade = self.last_trade_times.get(yf_ticker, 0)
        if time.time() - last_trade < COOLDOWN_SECONDS:
            remaining = int((COOLDOWN_SECONDS - (time.time() - last_trade)) / 60)
            # Silent skip - cooldown active
            return False
        # ========================================
        
        is_priority = ticker_data.get('priority', False)
        
        # Pre-check affordability for Capital.com (saves API calls & time)
        if self.broker == "capital" and not is_priority:
            try:
                if not self.client.can_afford_instrument(t212_ticker, self.trade_amount):
                    # Silent skip - too expensive
                    return False
            except:
                pass  # Continue if check fails

        try:
            strategy = Strategy(yf_ticker)
            # Pro Mean Reversion použij hodinová data (lepší výsledky)
            data_interval = "1h" if self.strategy_type == "mean_reversion" else INTERVAL
            data_period = "1mo" if self.strategy_type == "mean_reversion" else PERIOD

            df = strategy.fetch_data(period=data_period, interval=data_interval)
            if df.empty: return False

            # Vyber strategii podle nastavení
            if self.strategy_type == "mean_reversion":
                result = self.mean_reversion.get_signal(df)
                signal = result.get("signal")  # Mean reversion vrací "signal" místo "action"
            else:
                df = strategy.calculate_indicators(df)
                result = strategy.get_signal(df, self.strategy_config)
                signal = result.get("action")
            
            # Feed scanner table for dashboard
            ticker_show = yf_ticker
            priority_marker = "⭐ " if is_priority else ""
            self.scan_results.append({
                "Time": time.strftime("%H:%M:%S"),
                "Ticker": f"{priority_marker}{ticker_show}",
                "Action": signal,
                "RSI": round(result.get("rsi", 0), 1),
                "Reason": result.get("reason", ""),
                "Price": round(float(df.iloc[-1]["Close"]), 4),
            })
            if len(self.scan_results) > 200:
                self.scan_results.pop(0)
            rsi = result.get("rsi", 50)
            reason = result.get("reason", "")
            
            # Log interesting rejections (Low RSI but no Buy)
            if rsi < 35 and signal != "BUY":
                 self.log(f"[{yf_ticker}] Skipped (RSI {rsi:.2f}): {reason}")
            
            if signal in ["BUY", "SELL"]:
                # Check Limit
                positions = self.client.get_positions()
                max_pos = getattr(self, 'max_positions', MAX_POSITIONS)
                if len(positions) >= max_pos:
                    self.log(f"[LIMIT] Max positions ({max_pos}) reached. Skipping {t212_ticker}.")
                    return False
                
                # ========================================
                # DUPLICATE PROTECTION - Don't open same instrument twice!
                # ========================================
                for p in positions:
                    existing_epic = ""
                    if self.broker == "capital":
                        mkt = p.get('market', {}) or {}
                        pos = p.get('position', {}) or {}
                        existing_epic = mkt.get('epic') or pos.get('epic', '')
                    else:
                        existing_epic = p.get('ticker', '')
                    
                    if existing_epic.upper() == t212_ticker.upper():
                        self.log(f"[SKIP] Already have position in {t212_ticker}")
                        return False
                # ========================================

                self.log(f"[{yf_ticker}] {signal} SIGNAL! RSI: {rsi:.2f} | {reason}")
                
                # Logic differs slightly for CFD (Lot size) vs Stock (Quantity)
                if self.broker == "capital":
                    # Capital.com: Get instrument info for min size
                    last_price = df.iloc[-1]['Close']
                    if last_price <= 0:
                        self.log(f"Invalid price for {t212_ticker}: {last_price}")
                        return False

                    # Get actual minimum size from API
                    try:
                        inst_info = self.client.get_instrument_info(t212_ticker)
                        min_size = inst_info.get('min_size', 0.1)
                        max_size = inst_info.get('max_size', 100000)
                    except:
                        min_size = 0.1
                        max_size = 100000

                    # Calculate quantity based on trade amount
                    raw_qty = self.trade_amount / last_price
                    qty = round(raw_qty, 2)

                    # Enforce API minimum
                    if qty < min_size:
                        # Check if we can afford minimum (with margin ~3-5%)
                        min_cost = min_size * last_price * 0.03  # ~3% margin for CFDs
                        if min_cost > self.trade_amount:
                            self.log(f"Skipping {t212_ticker}: Min size {min_size} needs ${min_cost:.2f} margin")
                            return False
                        qty = min_size

                    # Cap at max size
                    if qty > max_size:
                        qty = max_size

                    # Get protection levels from strategy
                    stop_price = result.get("sl")
                    limit_price = result.get("tp")

                    val = qty * last_price
                    action_word = "Buying" if signal == "BUY" else "Shorting"
                    self.log(f"{action_word} {qty} of {t212_ticker} @ ${last_price:.4f} (Min: {min_size})")
                    self.log(f"Protection: SL {stop_price}, TP {limit_price}")

                    try:
                        # Capital Client place_market_order(epic, size, direction, sl, tp)
                        order_result = self.client.place_market_order(
                            t212_ticker,
                            qty,
                            direction=signal,
                            stop_loss=stop_price,
                            take_profit=limit_price,
                            trailing_stop=False  # Disable trailing - causes issues
                        )
                        self.log(f"✅ {signal} Order CONFIRMED: {order_result.get('dealReference', 'OK')}")
                        self.last_trade_times[yf_ticker] = time.time()
                        return True
                    except Exception as e:
                        self.log(f"❌ Order REJECTED: {e}")
                        return False

                else:
                    # Trading 212 Logic (Value calc)
                    last_price = df.iloc[-1]['Close']
                    rate = 1.0
                    if currency == 'USD': rate = 24.5
                    elif currency == 'EUR': rate = 25.2
                    elif currency == 'GBP': rate = 31.0
                    elif currency == 'GBX': rate = 0.31
                    
                    price_czk = last_price * rate
                    if price_czk == 0: price_czk = 100
                    
                    # Use instance variable self.trade_amount (CZK)
                    qty = round(self.trade_amount / price_czk, 4)
                    if qty <= 0: qty = 0.01

                    val_czk = price_czk * qty
                    self.log(f"Buying {qty} of {t212_ticker} (~{val_czk:.0f} CZK)")
                    
                    try:
                        self.client.place_market_order(t212_ticker, qty)
                        time.sleep(5) # Wait for fill
                        
                        stop_price = result.get("sl")
                        limit_price = result.get("tp")
                        
                        self.client.place_stop_order(t212_ticker, -qty, stop_price)
                        self.client.place_limit_order(t212_ticker, -qty, limit_price)
                        self.log(f"Trade Protected (SL: {stop_price}, TP: {limit_price})")
                        self.last_trade_times[yf_ticker] = time.time()
                        return True
                    except Exception as e:
                        self.log(f"Order failed: {e}")
                        return False
        except Exception as e:
            # self.log(f"Error {yf_ticker}: {e}")
            pass
        return False

    def scan_cycle(self):
        self.update_daily_pnl()
        if self.session_stopped_reason == "daily_loss":
            self.log(f"[SESSION] Daily loss limit reached (PnL: {getattr(self, 'daily_pnl', 0):.2f}). No new trades today.")
            return
        if self.session_stopped_reason == "profit_target":
            self.log(f"[SESSION] Daily profit target hit (PnL: {getattr(self, 'daily_pnl', 0):.2f}). No new trades.")
            return

        if not self.open_instruments:
            self.get_open_markets()
        if not self.open_instruments:
            self.log("No markets open.")
            return

        subset = self.open_instruments
        if len(subset) > MAX_SCAN_PER_CYCLE:
             subset = random.sample(self.open_instruments, MAX_SCAN_PER_CYCLE)
        self.log(f"Scanning {len(subset)} assets...")
        for item in subset:
            if not self.is_running:
                break
            self.process_instrument(item)
            time.sleep(1)


    def start_loop(self):
        """Starts the main loop in a thread."""
        if self.is_running: return
        self.is_running = True
        self.log("Starting bot loop...")
        
        def run():
            try:
                self.initialize_data()
                while self.is_running:
                    self.update_cache() # Keep UI fresh
                    self.scan_cycle()
                    for _ in range(30): # Faster loop for scalping (30s)
                        if not self.is_running: break
                        time.sleep(1)
            except Exception as e:
                self.log(f"CRITICAL THREAD ERROR: {e}")
            finally:
                self.is_running = False
                self.log("Bot loop terminated.")

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop_loop(self):
        self.is_running = False

# For backward compatibility if run directly
if __name__ == "__main__":
    api_key = os.getenv("T212_API_KEY")
    base_url = os.getenv("T212_BASE_URL")
    if api_key:
        bot = TradingBot(api_key, base_url)
        bot.start_loop()
        while True:
            time.sleep(1)
