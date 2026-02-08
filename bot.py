import time
import os
import random
import threading
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from client import Trading212Client
from strategy import Strategy
from mean_reversion_strategy import MeanReversionStrategy
from hybrid_strategy import HybridStrategy
from elite_strategy import EliteStrategy
from elite_strategy_v2 import EliteStrategyV2
from session_volume_profile import SessionVolumeProfile
from market_utils import is_market_open, map_ticker_to_yf
from learning_engine import get_learning_engine
from smart_analysis import get_smart_analyst
from telegram_notifier import get_telegram_notifier
from economic_data import get_economic_calendar

load_dotenv()

# =====================================================
# LIVE DEPLOYMENT CONFIGURATION (v3.2 - FINAL LIVE DEPLOY)
# =====================================================
# BEZPEČNOSTNÍ NASTAVENÍ PRO MALÝ ÚČET (2000-3000 Kč)

# MODE TOGGLE
DRY_RUN = False  # v3.2: START IN DRY-RUN — verify signals first, then set False

# API MODE - "demo" nebo "live"
CAPITAL_MODE = os.getenv("CAPITAL_MODE", "live")  # Default demo pro bezpečnost

# ULTRA-CONSERVATIVE SETTINGS (pro první live týden)
LIVE_SAFE_MODE = False  # Zapni pro extra bezpečnost

if LIVE_SAFE_MODE:
    MAX_POSITIONS = 4          # v3.2: Sníženo z 4 na 3 pro bezpečnost
    TRADE_AMOUNT_CZK = 200     # ~$7 per trade
    MAX_RISK_PCT = 0.002       # v3.2: START at 0.2% (ramps up after 20 trades)
else:
    MAX_POSITIONS = 5          # Normal mode
    TRADE_AMOUNT_CZK = 200     # ~$8 per trade
    MAX_RISK_PCT = 0.005       # 0.5% risk

# === RISK RAMP-UP SCHEDULE (v3.2) ===
RISK_RAMP_SCHEDULE = {
    0: 0.002,    # Trades 1-20: 0.2% risk (ultra-safe validation)
    20: 0.003,   # Trades 21-50: 0.3% risk (building confidence)
    50: 0.005,   # Trades 51+: 0.5% risk (full operational)
}

# === SAFETY LIMITS (v3.2) ===
MAX_CONSECUTIVE_LOSSES = 3     # Auto-pause after 3 consecutive losses
DRAWDOWN_ALERT_PCT = 3.0       # Telegram alert at 3% drawdown
DRAWDOWN_EMERGENCY_PCT = 8.0   # Emergency stop at 8% drawdown

SL_PCT = 0.01              # Fallback
TP_PCT = 0.02              # Fallback
MAX_SCAN_PER_CYCLE = 20    # Focused scan only
INTERVAL = "15m"           # 15m timeframe for Scalping/DayTrading
PERIOD = "60d"             # 60 days (Max buffer for 15m data on YF)

# Learning-based watchlist - BOT SI SÁM VYBERE NEJLEPŠÍ
TARGET_WATCHLIST_SIZE = 15 # Only top 15 assets
MIN_TRADES_FOR_RANK = 3

from capital_client import CapitalClient

class TradingBot:
    def __init__(self, api_key, base_url, broker="t212", cap_login=None, cap_pass=None):
        self.broker = broker
        self.api_key = api_key
        self.trade_amount = TRADE_AMOUNT_CZK
        self.small_account_mode = True
        
        # === DRY-RUN MODE ===
        self.dry_run = DRY_RUN
        self.live_safe_mode = LIVE_SAFE_MODE
        
        # === API URL SELECTION ===
        # Automaticky vybere demo/live URL podle CAPITAL_MODE
        if self.broker == "capital":
            if CAPITAL_MODE == "live":
                live_url = os.getenv("CAPITAL_LIVE_URL", "https://api-capital.backend-capital.com")
                self.client = CapitalClient(api_key, cap_login, cap_pass, live_url)
                print(f"⚠️ LIVE MODE: Připojeno k {live_url}")
            else:
                self.client = CapitalClient(api_key, cap_login, cap_pass, base_url)
                print(f"🔵 DEMO MODE: Připojeno k {base_url}")
        else:
            self.client = Trading212Client(api_key, base_url)
            
        self.is_running = False
        self.log_messages = []
        self.instruments = []
        self.open_instruments = []
        self._thread = None
        self.max_positions = MAX_POSITIONS

        # === STRATEGY SELECTION (v5.0) ===
        # "elite_v2" = EliteStrategyV2 (VWAP Bands + VP Regime Engine) — RECOMMENDED
        # "hybrid" = HybridStrategy (ADX Switch: Trend/Range)
        # "elite" = EliteStrategy v1 (VWAP + VP + Confluence)
        self.strategy_type = "elite_v2"
        
        # =====================================================
        # ELITE STRATEGY CONFIG (15m)
        # =====================================================
        self.strategy_config = {
            "rsi_buy": 60,
            "rsi_oversold": 40,
            "rsi_sell": 40,
            "rsi_overbought": 60,
            "adx_min": 22,               # v5.0: Wider ADX range (was 25) — more trend signals
            "risk_reward": 1.3,          # v5.0: R:R 1.3 minimum (was 2.0)
            "atr_sl_mult": 4.0,          # v5.0: Base ATR mult (was 3.0, overridden per asset class)
            "max_risk_pct": MAX_RISK_PCT,
            "min_rr_ratio": 1.3,         # v5.0: was 2.0 — allow wider SLs with lower R:R
            "st_period": 10,
            "st_multiplier": 3.0,
            "hma_fast": 9,
            "hma_slow": 21,
            "min_confluence": 3,         # v5.0: 3 indicators (VP + 2 others)
        }
        
        # === HIGH VOLUME SETTINGS ===
        # ZAPNUTO - používáme v2.0 safe aggressive logiku (RSI 35/65, ne 55/45)
        self.aggressive_mode = True

        # =====================================================
        # SELF-LEARNING ENGINE
        # =====================================================
        # Bot se učí z vlastních obchodů a automaticky optimalizuje
        self.learning_engine = get_learning_engine(use_supabase=True)
        
        # Get learned parameters (or use defaults)
        learned = self.learning_engine.get_learned_params()
        
        self.smart_analyst = get_smart_analyst()
        self.telegram = get_telegram_notifier()
        
        self.trade_amount = 250.0   # v5.0: Target Risk per trade (CZK) — FIXED, not overridden

        # Risk Management (v5.0 Update — PROFIT OPTIMIZATION)
        self.dry_run = getattr(self, "dry_run", DRY_RUN)
        self.max_risk_pct = 0.30 # v5.0: Max risk 30% equity to allow crypto min sizes (BTC 0.01)

        # Daily Limits (v5.0 — FINAL, NOT OVERRIDDEN BELOW)
        self.daily_profit_target = 400.0  # CZK — Stop trading for the day when hit
        self.max_daily_loss = 100.0       # CZK — Stop trading, protect from minus day
        self.daily_pnl = 0.0
        self.daily_reset_date = date.today().isoformat()
        self.session_stopped_reason = None # "daily_loss", "profit_target", "drawdown"
        if learned:
             # Adapt only slightly
             pass

        # STRATEGY INIT (v5.0: EliteStrategyV2 is primary)
        self.elite_strategy_v2 = EliteStrategyV2(self.strategy_config)
        self.elite_strategy = EliteStrategy(self.strategy_config)  # Fallback
        self.hybrid_strategy = HybridStrategy(self.strategy_config)
        self.mean_reversion = self.hybrid_strategy.mean_reversion

        # Session Volume Profile (v5.1)
        self.session_vp = SessionVolumeProfile(num_bins=30, value_area_pct=0.70)

        self.log(f"🧠 EliteStrategy V2 (VWAP Bands + VP Regime) Initialized.")
        self.log(f"📊 Timeframe: {INTERVAL}, Period: {PERIOD}")

        # UI & Strategy State (Initialized here for immediate access)
        self.scan_results = []
        self.last_trade_times = {}
        
        # =====================================================
        # BLACKLIST
        # =====================================================
        self.ticker_blacklist = [
            "LTCUSD", "LTC-USD", # Still choppy often
            "Si=F", "Silver", # Spreads
        ]
        
        # =====================================================
        # ELITE 15 WATCHLIST - The 15 Best Assets (Forex & Crypto)
        # =====================================================
        self.priority_tickers = [
            # === CRYPTO (High Volatility, Good Trends) ===
            {"epic": "BTCUSD", "yf": "BTC-USD", "name": "Bitcoin", "cat": "Crypto"},
            {"epic": "ETHUSD", "yf": "ETH-USD", "name": "Ethereum", "cat": "Crypto"},
            {"epic": "SOLUSD", "yf": "SOL-USD", "name": "Solana", "cat": "Crypto"},
            {"epic": "BNBUSD", "yf": "BNB-USD", "name": "Binance Coin", "cat": "Crypto"}, # Added
            {"epic": "XRPUSD", "yf": "XRP-USD", "name": "Ripple", "cat": "Crypto"},       # Unblacklisted

            # === FOREX MAJORS (Reliable Liquidity for VP) ===
            {"epic": "EURUSD", "yf": "EURUSD=X", "name": "EUR/USD", "cat": "Forex"},
            {"epic": "GBPUSD", "yf": "GBPUSD=X", "name": "GBP/USD", "cat": "Forex"},
            {"epic": "USDJPY", "yf": "USDJPY=X", "name": "USD/JPY", "cat": "Forex"},
            {"epic": "AUDUSD", "yf": "AUDUSD=X", "name": "AUD/USD", "cat": "Forex"},
            {"epic": "USDCAD", "yf": "USDCAD=X", "name": "USD/CAD", "cat": "Forex"},
            {"epic": "NZDUSD", "yf": "NZDUSD=X", "name": "NZD/USD", "cat": "Forex"},
            {"epic": "USDCHF", "yf": "USDCHF=X", "name": "USD/CHF", "cat": "Forex"},

            # === FOREX CROSSES (Structure) ===
            {"epic": "EURGBP", "yf": "EURGBP=X", "name": "EUR/GBP", "cat": "Forex"},
            {"epic": "GBPJPY", "yf": "GBPJPY=X", "name": "GBP/JPY", "cat": "Forex"},
            {"epic": "EURJPY", "yf": "EURJPY=X", "name": "EUR/JPY", "cat": "Forex"},
        ]
        # Total: 15 Assets
        
        # Pass protected list to Learning Engine to prevent auto-ban
        self.protected_tickers = [t["yf"] for t in self.priority_tickers]
        if hasattr(self.learning_engine, 'set_protected_tickers'):
            self.learning_engine.set_protected_tickers(self.protected_tickers)

        # =====================================================
        # AGGRESSIVE MODE - Cíl: 100% měsíčně (2000→4000 Kč)
        # =====================================================
        # Potřeba: ~4.5% denně = ~$3.50/den při $80 kapitálu
        # S pákou 1:20 = potřeba ~0.23% pohyb na obchod

        # v5.0: Daily limits are set ABOVE (lines ~147-151). DO NOT overwrite here!
        # self.daily_pnl, daily_reset_date, session_stopped_reason already set above.
        self._daily_pnl_lock = threading.Lock()

        # Position sizing (v5.0)
        self.margin_usage_pct = 0.50  # v5.0: 50% marginu (was 40%)
        self.max_positions = MAX_POSITIONS

        # Kelly Criterion - based on realistic backtest (45% WR)
        self.kelly_win_rate = 0.45    # 45% WR z backtestu (realistické)
        self.kelly_avg_win = 1.5      # R:R 1.5
        self.kelly_avg_loss = 1.0
        self.kelly_fraction = 0.25    # 25% Kelly (konzervativní)

        # Correlation filter (v5.0: prioritize crypto for bigger moves)
        self.max_forex_positions = 3   # v5.0: was 2
        self.max_crypto_positions = 4  # v5.0: was 3 — crypto = main profit source
        self.max_stock_positions = 1

        # Drawdown protection (v3.2: tiered alerts)
        self.max_drawdown_pct = DRAWDOWN_EMERGENCY_PCT  # 8% emergency stop
        self.drawdown_alert_pct = DRAWDOWN_ALERT_PCT    # 3% telegram alert
        self.initial_balance = None
        self._drawdown_alerted = False  # Track if alert already sent

        # Spread filter (v5.0: relaxed for crypto)
        self.max_spread_pct = 0.25    # v5.0: Max 0.25% spread (was 0.10 — too strict for crypto)

        # Trade tracking
        self.session_trades = []
        self.wins = 0
        self.losses = 0

        # === v3.2: CONSECUTIVE LOSS TRACKER + AUTO-PAUSE ===
        self._consecutive_losses = 0
        self._auto_paused = False
        self._total_live_trades = 0  # Counter for risk ramp-up

        # === v3.3: SAFETY STARTUP ===
        self.startup_cycles = 0  # Counter for auto-dry-run
        self.min_dry_run_cycles = 5 # Force dry run for first 5 scans

        # Compounding - zvyšuj trade_amount s profitem
        self.compound_profits = True
        self.base_capital = 2000.0      # 2000 Kč (LIVE účet v CZK)

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
        
        # =====================================================
        # SELF-LEARNING: Record past trades and optimize
        # =====================================================
        if hasattr(self, 'learning_engine'):
            self.log("🧠 Learning Engine: Analyzing past trades...")
            self.record_closed_trades()  # Learn from recent closed trades
            self.optimize_learning()      # Optimize parameters
            
            # Show learning summary
            summary = self.learning_engine.get_stats_summary()
            self.log(f"🧠 Tracked: {summary['total_trades']} trades, "
                     f"WR: {summary['overall_win_rate']:.0f}%, "
                     f"Blacklisted: {summary['auto_blacklisted_count']} tickers")

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
        """
        SMART COMPOUNDING v2.0
        - Base: Grow trade_amount with account balance
        - Streak Adjustment: Reduce after losses, increase after wins
        - Anti-Tilt: Hard cap after 3+ consecutive losses
        """
        if not self.compound_profits:
            return

        try:
            acc = self.client.get_account_info()
            accounts = acc.get('accounts', [])
            if not accounts:
                return
                
            balance = accounts[0].get('balance', {}).get('balance', 0)
            available = accounts[0].get('balance', {}).get('available', 0)

            if balance <= 0:
                return
                
            # === BASE COMPOUND (v5.0: Higher base for real profits) ===
            growth_factor = balance / self.base_capital
            base_trade_amount = min(
                available * self.margin_usage_pct / self.max_positions,
                balance * 0.15  # v5.0: Max 15% účtu per trade (was 8%)
            )
            # v5.0: Never go below 250 CZK target
            base_trade_amount = max(250.0, base_trade_amount)
            
            # === STREAK ADJUSTMENT ===
            # Track wins/losses
            wins = getattr(self, 'wins', 0)
            losses = getattr(self, 'losses', 0)
            
            # Calculate current streak
            if not hasattr(self, '_last_results'):
                self._last_results = []
            
            streak_multiplier = 1.0
            
            if len(self._last_results) >= 2:
                # Check for losing streak
                recent_losses = sum(1 for r in self._last_results[-3:] if r == 'L')
                recent_wins = sum(1 for r in self._last_results[-3:] if r == 'W')
                
                if recent_losses >= 3:
                    # ANTI-TILT: 3+ consecutive losses = reduce to 50%
                    streak_multiplier = 0.5
                    self.log("🛡️ ANTI-TILT: Reducing position size after loss streak")
                elif recent_losses >= 2:
                    # 2 losses = reduce to 75%
                    streak_multiplier = 0.75
                elif recent_wins >= 3:
                    # 3+ wins = boost to 125%
                    streak_multiplier = 1.25
                    self.log("🔥 HOT STREAK: Increasing position size")
                elif recent_wins >= 2:
                    # 2 wins = boost to 110%
                    streak_multiplier = 1.1
            
            # Apply streak adjustment
            adjusted_amount = base_trade_amount * streak_multiplier

            # v5.0: Clamp — min 250 CZK (target risk), max 800 CZK
            # Never go below 250 CZK to maintain meaningful position sizes
            self.trade_amount = max(250.0, min(800.0, adjusted_amount))

            if growth_factor > 1.1:
                self.log(f"📈 COMPOUND: Balance ${balance:.2f} (+{(growth_factor-1)*100:.0f}%), Trade: ${self.trade_amount:.2f} (x{streak_multiplier:.2f})")
        except:
            pass
    
    def get_current_risk_pct(self):
        """v3.2: Get risk % based on ramp-up schedule."""
        trades = getattr(self, '_total_live_trades', 0)
        risk = MAX_RISK_PCT  # default
        for threshold in sorted(RISK_RAMP_SCHEDULE.keys(), reverse=True):
            if trades >= threshold:
                risk = RISK_RAMP_SCHEDULE[threshold]
                break
        return risk

    def record_trade_result(self, is_win):
        """Record trade result for streak tracking + auto-pause."""
        if not hasattr(self, '_last_results'):
            self._last_results = []

        self._last_results.append('W' if is_win else 'L')
        self._total_live_trades = getattr(self, '_total_live_trades', 0) + 1

        # Keep only last 10 results
        if len(self._last_results) > 10:
            self._last_results.pop(0)

        # Update counters
        if is_win:
            self.wins = getattr(self, 'wins', 0) + 1
            self._consecutive_losses = 0
        else:
            self.losses = getattr(self, 'losses', 0) + 1
            self._consecutive_losses = getattr(self, '_consecutive_losses', 0) + 1

        # === AUTO-PAUSE after MAX_CONSECUTIVE_LOSSES ===
        if self._consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            self._auto_paused = True
            self.log(f"🛑 AUTO-PAUSE: {self._consecutive_losses} consecutive losses! Trading paused.")
            if hasattr(self, 'telegram') and self.telegram.enabled:
                self.telegram.send_message(
                    f"🛑 <b>AUTO-PAUSE</b>\n\n"
                    f"{self._consecutive_losses} consecutive losses.\n"
                    f"Trading paused until manual resume.\n"
                    f"Total: {self.wins}W / {self.losses}L"
                )

        # Log risk ramp status
        risk_pct = self.get_current_risk_pct()
        self.log(f"📊 Trade #{self._total_live_trades}: {'WIN' if is_win else 'LOSS'} | "
                 f"Streak: {self._consecutive_losses}L | Risk: {risk_pct*100:.1f}%")

    def get_optimal_trade_size(self, epic, current_price):
        """Vypočítej optimální velikost pozice pro daný instrument."""
        try:
            # Získej info o instrumentu
            inst_info = self.client.get_instrument_info(epic)
            min_size = inst_info.get('min_size', 0.1)
            margin_factor = inst_info.get('margin_factor', 0.05)
            
            # Pevný kurz pro bezpečný výpočet (raději konzervativní)
            FX_USD_CZK = 24.0
            FX_EUR_CZK = 26.0
            
            # Aktualizuj trade_amount podle compoundingu (v CZK)
            self.update_trade_amount_compound()
            # self.trade_amount je nyní v CZK (např. 200)

            # Vypočítej velikost
            if current_price > 0:
                # 1. Konverze ceny instrumentu do CZK
                # Většina instrumentů je v USD (Crypto, US Stocks) nebo v Quote měně (Forex)
                # Pro zjednodušení předpokládáme, že pokud není měna CZK, musíme konvertovat
                
                # Odhad konverzního faktoru podle názvu (Crypto/Stocks = USD, Forex = Quote Ccy)
                conversion_rate = 1.0
                if "USD" in epic or "BTC" in epic or "ETH" in epic: # USD assets
                     conversion_rate = FX_USD_CZK
                elif "EUR" in epic: # Euro assets (pokud existují)
                     conversion_rate = FX_EUR_CZK
                
                # Výpočet Marginu na 1 jednotku v CZK
                # CostPerUnit_CZK = Price_Asset * Conversion * MarginFactor
                cost_per_unit_czk = current_price * conversion_rate * margin_factor
                
                if cost_per_unit_czk > 0:
                    raw_size = self.trade_amount / cost_per_unit_czk
                else:
                    raw_size = min_size

                # Zaokrouhli a ověř minimum
                # Pokud je vypočítaná velikost MENŠÍ než minimum, musíme zkontrolovat, 
                # jestli si můžeme dovolit to minimum.
                
                if raw_size < min_size:
                    # Check cost of min_size
                    min_cost_czk = min_size * cost_per_unit_czk
                    if min_cost_czk > (self.trade_amount * 1.5): # Povolíme max 50% překročení
                         self.log(f"⚠️ SKIP {epic}: Minimum size cost {min_cost_czk:.0f} CZK > Limit {self.trade_amount:.0f} CZK")
                         return 0, 0, 0 # Skip trade
                    else:
                         size = min_size
                else:
                    size = round(raw_size, 3) # TODO: Respektovat 'lot_step' from broker info
                
                # Final sanity check against decimals from broker info if available
                # Prozatím jen basic round
                step = inst_info.get('step', 0.01)
                if step: 
                    import math
                    # Round down to nearest step
                    size = math.floor(size / step) * step

                return size, min_size, margin_factor

            return min_size, min_size, margin_factor
        except Exception as e:
            self.log(f"Size Calc Error: {e}")
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
        """v3.2: Tiered drawdown protection with Telegram alerts."""
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

                    # Level 1: Alert at DRAWDOWN_ALERT_PCT (3%)
                    if drawdown_pct >= self.drawdown_alert_pct and not self._drawdown_alerted:
                        self._drawdown_alerted = True
                        self.log(f"⚠️ DRAWDOWN ALERT: -{drawdown_pct:.1f}% (threshold: {self.drawdown_alert_pct}%)")
                        if hasattr(self, 'telegram') and self.telegram.enabled:
                            self.telegram.send_message(
                                f"⚠️ <b>DRAWDOWN ALERT</b>\n\n"
                                f"Drawdown: <code>-{drawdown_pct:.1f}%</code>\n"
                                f"Balance: {balance:.0f} CZK\n"
                                f"Initial: {self.initial_balance:.0f} CZK\n\n"
                                f"Bot continues trading. Emergency stop at -{self.max_drawdown_pct:.0f}%."
                            )

                    # Level 2: Emergency stop at DRAWDOWN_EMERGENCY_PCT (8%)
                    if drawdown_pct >= self.max_drawdown_pct:
                        if hasattr(self, 'telegram') and self.telegram.enabled:
                            self.telegram.send_message(
                                f"🛑 <b>EMERGENCY STOP</b>\n\n"
                                f"Drawdown: <code>-{drawdown_pct:.1f}%</code>\n"
                                f"All trading stopped.\n"
                                f"Balance: {balance:.0f} CZK"
                            )
                        return False, f"EMERGENCY STOP: Drawdown -{drawdown_pct:.1f}%"

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

    def detect_asset_class(self, epic, yf_ticker=""):
        """Detect asset class for risk profile selection."""
        epic_upper = epic.upper()
        yf_upper = yf_ticker.upper()

        # Crypto detection
        crypto_tokens = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOT", "DOGE",
                         "AVAX", "LINK", "MATIC", "LTC", "UNI", "ATOM"]
        for token in crypto_tokens:
            if token in epic_upper or token in yf_upper:
                return "crypto"
        if "-USD" in yf_upper and "=" not in yf_upper:
            return "crypto"

        # Forex detection
        if "=X" in yf_upper:
            return "forex"
        forex_pairs = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
        if len(epic_upper) == 6 and any(c in epic_upper for c in forex_pairs):
            return "forex"

        return "default"

    def calculate_risk_based_size(self, epic, sl_distance, current_price, asset_class="default"):
        """
        Calculate position size based on risk management formula:
        qty = (equity × risk_pct) / (SL_distance_per_unit × conversion_rate)

        v3.2: Uses ramp-up schedule for risk_pct.
        """
        try:
            # Get account equity
            acc = self.client.get_account_info()
            accounts = acc.get('accounts', [])
            if not accounts:
                return 0

            equity = accounts[0].get('balance', {}).get('balance', 0)
            if equity <= 0:
                return 0

            # v5.0: CLEAN SIZING — target CZK risk directly
            # Conversion: most assets priced in USD
            FX_USD_CZK = 24.0
            FX_EUR_CZK = 26.0

            if "EUR" in epic.upper() and "USD" not in epic.upper():
                conversion = FX_EUR_CZK
            else:
                conversion = FX_USD_CZK

            # SL distance is in asset price units (e.g., $1900 for BTC, 0.0063 for EURUSD)
            risk_per_unit = sl_distance * conversion  # CZK risk per 1 unit of instrument

            if risk_per_unit <= 0:
                return 0

            # v5.0: Target risk = trade_amount (250 CZK), safe start 100 CZK
            target_risk_czk = self.trade_amount  # 250 CZK

            if getattr(self, '_total_live_trades', 0) < 10:
                target_risk_czk = 100.0  # Safe start: 100 CZK for first 10 trades
                self.log(f"🛡️ Safe start: Using 100 CZK risk (trade #{self._total_live_trades + 1}/10)")

            # Position size to risk exactly target_risk_czk on SL hit
            raw_qty = target_risk_czk / risk_per_unit

            # Get broker constraints
            inst_info = self.client.get_instrument_info(epic)
            min_size = inst_info.get('min_size', 0.01)
            max_size = inst_info.get('max_size', 100000)

            if raw_qty < min_size:
                # Check if min size risk is acceptable (max 20% of equity - bumped for crypto)
                min_risk_czk = min_size * sl_distance * conversion
                max_acceptable = equity * self.max_risk_pct  
                if min_risk_czk > max_acceptable:
                    self.log(f"⚠️ SKIP {epic}: Min size risk {min_risk_czk:.0f} CZK > {self.max_risk_pct*100:.0f}% equity ({max_acceptable:.0f} CZK)")
                    return 0
                raw_qty = min_size
                self.log(f"📐 {epic}: Using min size {min_size} (risk: {min_risk_czk:.1f} CZK)")

            # Round down to step
            step = inst_info.get('step', 0.01)
            if step and step > 0:
                import math
                raw_qty = math.floor(raw_qty / step) * step

            raw_qty = min(raw_qty, max_size)

            actual_risk = raw_qty * sl_distance * conversion
            self.log(f"📐 Risk Sizing: {raw_qty} × SL {sl_distance:.5f} = {actual_risk:.1f} CZK ({actual_risk/equity*100:.2f}% equity)")

            return raw_qty

        except Exception as e:
            self.log(f"Risk sizing error: {e}")
            return 0

    def set_active_categories(self, categories):
        """Update active scanning categories."""
        self.active_categories = categories
        self.log(f"Active Categories updated: {categories}")
        self.open_instruments = [] # Force refresh
        # Note: Current running cycle will finish with old list, next cycle will use new.

    def is_blacklisted(self, ticker):
        """Check if ticker is in blacklist (manual or auto-learned)."""
        # Check manual blacklist
        if hasattr(self, 'ticker_blacklist'):
            for bl in self.ticker_blacklist:
                if bl.upper() in ticker.upper():
                    return True
        
        # Check auto-blacklist from learning engine
        if hasattr(self, 'learning_engine'):
            is_auto_bl, reason = self.learning_engine.is_blacklisted(ticker)
            if is_auto_bl:
                # Log only occasionally to avoid spam
                return True
        
        return False

    def _dedupe_candidates(self, items):
        """Deduplicate candidate tickers by epic/yf."""
        seen = set()
        unique = []
        for item in items:
            epic = item.get("epic") or item.get("t212") or ""
            key = epic or item.get("yf", "")
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _build_candidate_pool(self):
        """Build candidate pool from priority and market categories."""
        candidates = []
        if hasattr(self, "priority_tickers"):
            candidates.extend(self.priority_tickers)

        # Add from market categories (Capital only)
        if hasattr(self, "market_categories") and hasattr(self, "active_categories"):
            for cat in self.active_categories:
                for item in self.market_categories.get(cat, []):
                    candidates.append(item)

        return self._dedupe_candidates(candidates)

    def _get_dynamic_watchlist(self, max_items=TARGET_WATCHLIST_SIZE):
        """
        Build a learning-based watchlist:
        - Best performers from learning engine
        - Some unexplored tickers (exploration)
        """
        candidates = self._build_candidate_pool()
        if not candidates:
            return []

        # Filter blacklisted
        filtered = []
        for c in candidates:
            epic = c.get("epic") or c.get("t212") or ""
            yf = c.get("yf", "")
            if self.is_blacklisted(epic) or (yf and self.is_blacklisted(yf)):
                continue
            filtered.append(c)

        if not filtered:
            return []

        # If no learning engine, fallback to first N
        if not hasattr(self, "learning_engine"):
            return filtered[:max_items]

        stats = self.learning_engine.ticker_stats

        # Score candidates by learning stats
        scored = []
        unexplored = []
        for c in filtered:
            epic = c.get("epic") or c.get("t212") or ""
            st = stats.get(epic)
            if not st or st.get("trades", 0) < MIN_TRADES_FOR_RANK:
                unexplored.append(c)
                continue
            score = st.get("profit_factor", 0) * 100 + st.get("win_rate", 0)
            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        best = [c for _, c in scored]

        # Mix: 60% best, 30% exploration, 10% fill
        # For Small Accounts: Be MUCH more conservative with exploration
        if getattr(self, 'small_account_mode', False):
             # 80% Best, 10% Exploration, 10% Fill
             best_n = max(1, int(max_items * 0.8))
             explore_n = max(1, int(max_items * 0.1)) # Only ~2 new assets
        else:
             # Standard: 60% / 30% / 10%
             best_n = max(1, int(max_items * 0.6))
             explore_n = max(1, int(max_items * 0.3))
             
        watchlist = []
        
        # 1. Add Best Candidates (Limit: best_n)
        watchlist.extend(best[:best_n])
        
        # 2. Smart Exploration (Limit: explore_n)
        # Prioritize unexplored assets with good Analyst Ratings
        smart_unexplored = []
        regular_unexplored = []
        
        # Only do this if we have the smart analyst loaded
        if hasattr(self, 'smart_analyst') and self.broker == "capital":
            for c in unexplored:
                # Basic pre-filter to save API calls
                yf = c.get('yf', '')
                
                # STRICT FILTER: Only scan US Stocks for Analyst Ratings
                # Skip Forex (=X), Crypto (-USD), Commodities (=F)
                if not yf or "=" in yf or "-" in yf:
                     regular_unexplored.append(c)
                     continue
                     
                try:
                    # Quick check (cached)
                    rating = self.smart_analyst.get_analyst_rating(yf)
                    if rating.get('score', 0) > 0.5: # Buy/Strong Buy
                        smart_unexplored.append(c)
                    else:
                        regular_unexplored.append(c)
                except:
                    regular_unexplored.append(c)
        else:
             regular_unexplored = unexplored

        # Add Smart Picks first
        needed_explore = explore_n
        if smart_unexplored:
             self.log(f"🔎 Discovery: Found {len(smart_unexplored)} promising new assets!")
             take = min(len(smart_unexplored), needed_explore)
             watchlist.extend(smart_unexplored[:take])
             needed_explore -= take
             
        # Fill rest of exploration quota with random regular items
        if needed_explore > 0 and regular_unexplored:
             watchlist.extend(regular_unexplored[:needed_explore])

        # 3. Fill the rest of the capacity (Fill Quota)
        # If 'Best' list was empty (new bot), this will ensure we still have a full watchlist
        slots_left = max_items - len(watchlist)
        if slots_left > 0:
            remaining = [c for c in filtered if c not in watchlist]
            
            # For Small Accounts, prefer lower volatility fillers if available? 
            # For now, just fill up to the limit.
            watchlist.extend(remaining[:slots_left])

        return watchlist[:max_items]

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
        
        # Manual List for US Stocks - EMPTIED to enforce Elite 15 Strategy
        self.market_categories["US Stocks"] = []
        
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
                        # Capital: BTCUSD -> YF: BTC-USD
                        yf_ticker = f"{epic.replace('USD', '')}-USD"
                    elif cat_name == "Commodities":
                        # Basic mapping
                        if "Gold" in name: yf_ticker = "GC=F"
                        elif "Silver" in name: yf_ticker = "SI=F"
                        elif "Oil" in name or "Brent" in name: yf_ticker = "BZ=F"
                    elif cat_name == "Indices":
                        if "US500" in name: yf_ticker = "^GSPC"
                        elif "US30" in name: yf_ticker = "^DJI"
                        elif "DE40" in name: yf_ticker = "^GDAXI"

                    if yf_ticker:
                        # Skip blacklisted YF tickers
                        if self.is_blacklisted(yf_ticker):
                            continue
                        self.market_categories[cat_name].append({
                            'epic': epic,
                            'yf': yf_ticker,
                            'name': name
                        })
                        
            except Exception as e:
                self.log(f"Error scanning {cat_name}: {e}")
                
            # FALLBACK: If API failed or found nothing, use Static List
            if not self.market_categories.get(cat_name) and cat_name != "US Stocks":
                self.log(f"⚠️ Using Fallback List for {cat_name}")
                self.market_categories[cat_name] = self._get_fallback_markets(cat_name)

        # Log summary
        total = sum(len(v) for v in self.market_categories.values())
        self.log(f"Scan Complete. Total markets: {total} (Blacklisted excluded)")

    def _get_fallback_markets(self, category):
        """Static list of popular assets if dynamic scan fails."""
        if category == "Forex":
            return [
                {"epic": "EURUSD", "yf": "EURUSD=X", "name": "EUR/USD"},
                {"epic": "GBPUSD", "yf": "GBPUSD=X", "name": "GBP/USD"},
                {"epic": "USDJPY", "yf": "USDJPY=X", "name": "USD/JPY"},
                {"epic": "AUDUSD", "yf": "AUDUSD=X", "name": "AUD/USD"},
                {"epic": "USDCAD", "yf": "USDCAD=X", "name": "USD/CAD"},
                {"epic": "USDCHF", "yf": "USDCHF=X", "name": "USD/CHF"},
                {"epic": "NZDUSD", "yf": "NZDUSD=X", "name": "NZD/USD"},
                {"epic": "EURGBP", "yf": "EURGBP=X", "name": "EUR/GBP"},
                {"epic": "EURJPY", "yf": "EURJPY=X", "name": "EUR/JPY"},
                {"epic": "GBPJPY", "yf": "GBPJPY=X", "name": "GBP/JPY"}
            ]
        elif category == "Crypto":
            return [
                {"epic": "BTCUSD", "yf": "BTC-USD", "name": "Bitcoin"},
                {"epic": "ETHUSD", "yf": "ETH-USD", "name": "Ethereum"},
                {"epic": "LTCUSD", "yf": "LTC-USD", "name": "Litecoin"},
                {"epic": "XRPUSD", "yf": "XRP-USD", "name": "Ripple"}
            ]
        elif category == "Commodities":
            return [
                {"epic": "Gold", "yf": "GC=F", "name": "Gold"},
                {"epic": "Silver", "yf": "SI=F", "name": "Silver"},
                {"epic": "Oil - US Crude", "yf": "CL=F", "name": "Crude Oil"},
                {"epic": "Oil - Brent Crude", "yf": "BZ=F", "name": "Brent Oil"}
            ]
        elif category == "Indices":
            return [
                {"epic": "US500", "yf": "^GSPC", "name": "S&P 500"},
                {"epic": "US30", "yf": "^DJI", "name": "Dow Jones"},
                {"epic": "US100", "yf": "^NDX", "name": "Nasdaq 100"},
                {"epic": "DE40", "yf": "^GDAXI", "name": "DAX 40"},
                {"epic": "UK100", "yf": "^FTSE", "name": "FTSE 100"}
            ]
        return []

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
            if getattr(self, 'small_account_mode', False):
                # Learning-based watchlist (best + exploration)
                dynamic_list = self._get_dynamic_watchlist(TARGET_WATCHLIST_SIZE)
                if not dynamic_list and hasattr(self, 'priority_tickers'):
                    dynamic_list = self.priority_tickers

                for pt in dynamic_list:
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
            self.log(f"[{yf_ticker}] Skipped - Blacklisted")
            return False
        
        # ========================================
        # COOLDOWN - Wait 15 min before trading same direction on same instrument
        # NOVÉ: Povoluje opačný směr (hedging) i během cooldownu
        # ========================================
        COOLDOWN_SECONDS = 900  # 15 minutes
        
        # Uložíme jako tuple: (time, direction) místo jen time
        last_trade_info = self.last_trade_times.get(yf_ticker)
        
        if last_trade_info:
            last_time, last_direction = last_trade_info if isinstance(last_trade_info, tuple) else (last_trade_info, None)
            
            if time.time() - last_time < COOLDOWN_SECONDS:
                # Cooldown je aktivní - ale povolíme opačný směr
                # (last_direction bude nastaveno později po signálu, prozatím skip check)
                pass  # Kontrola směru bude provedena po získání signálu
        # ========================================
        
        is_priority = ticker_data.get('priority', False)
        
        # Pre-check affordability for Capital.com (saves API calls & time)
        if self.broker == "capital" and not is_priority:
            try:
                # Get Info (Status + Limits)
                info = self.client.get_instrument_info(t212_ticker)
                
                # 1. Market Status Check
                status = info.get('market_status', 'UNKNOWN')
                if status not in ['TRADEABLE', 'OPEN']:
                    self.log(f"[{yf_ticker}] Market Closed ({status}) - Skipping")
                    return False

                # 2. Affordability Check
                # Re-use info to save API call in can_afford (optimization needed there or just do it here)
                # For now, simplistic check using fetched info
                min_size = info.get('min_size', 0.1)
                bid = info.get('bid', 0)
                margin = info.get('margin_factor', 0.05)
                req_margin = min_size * bid * margin
                
                if req_margin > self.trade_amount:
                     self.log(f"[{yf_ticker}] Cannot afford (Req: {req_margin:.2f}, Avail: {self.trade_amount}) - Skipping")
                     return False
            except Exception as e:
                self.log(f"[{yf_ticker}] Pre-flight check failed: {e}")

        try:
            strategy = Strategy(yf_ticker)
            # Pro scalping použij 5m data
            data_interval = INTERVAL  # 5m pro všechny strategie
            data_period = PERIOD      # 5d dat

            # Fetch data (Normal)
            df = strategy.fetch_data(period=data_period, interval=data_interval)
            
            # Fetch Trend Data (4h) for MTF
            df_trend = strategy.fetch_trend_data()
            major_trend = strategy.get_trend_direction(df_trend)
            
            if df.empty:
                # Still show in scanner with "NO DATA" status
                self.scan_results.append({
                    "Time": time.strftime("%H:%M:%S"),
                    "Ticker": yf_ticker,
                    "Action": "SKIP",
                    "RSI": 0,
                    "Reason": "No data from yfinance",
                    "Price": 0,
                })
                return False

            # Detect asset class for risk profile
            asset_class = self.detect_asset_class(t212_ticker, yf_ticker)

            # v5.0: Strategy selection — elite_v2 is primary
            if self.strategy_type == "elite_v2":
                # === ELITE STRATEGY V2 (VWAP Bands + VP Regime Engine) ===
                result = self.elite_strategy_v2.get_signal(df, asset_class=asset_class)
                signal = result.get("signal")
                confidence = result.get("confidence", 0)
                regime = result.get("regime", "UNKNOWN")
                strategy_used = result.get("strategy", "ELITE_V2")

            elif self.strategy_type == "elite":
                # === ELITE STRATEGY v1 (fallback) ===
                result = self.elite_strategy.get_signal(df, asset_class=asset_class)
                signal = result.get("signal")
                confidence = result.get("confidence", 0)
                regime = "TREND" if result.get("adx", 0) > 25 else "RANGING"
                strategy_used = "ELITE_VP"

            elif self.strategy_type == "hybrid" or self.strategy_type == "mean_reversion":
                # === HYBRID STRATEGY ===
                result = self.hybrid_strategy.get_signal(df, major_trend=major_trend, asset_class=asset_class)
                signal = result.get("signal")
                regime = result.get("regime", "UNKNOWN")
                strategy_used = result.get("strategy", "HYBRID_AUTO")
            else:
                df = strategy.calculate_indicators(df)
                result = strategy.get_signal(df, self.strategy_config)
                signal = result.get("action")
                regime = "UNKNOWN"
                strategy_used = "LEGACY"
            
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
            
            # ========================================
            # SESSION VOLUME PROFILE — confidence booster
            # ========================================
            if signal in ["BUY", "SELL"]:
                try:
                    svp_result = self.session_vp.analyze(df)
                    if svp_result and svp_result.get("levels"):
                        svp_score, svp_reasons = self.session_vp.get_signal_score(
                            float(df.iloc[-1]["Close"]),
                            svp_result["levels"],
                            signal,
                        )
                        # Boost confidence by up to +15% based on VP alignment
                        svp_boost = min(svp_score * 0.03, 0.15)
                        confidence = result.get("confidence", 0) + svp_boost
                        result["confidence"] = confidence
                        if svp_reasons:
                            result["reason"] = result.get("reason", "") + " | SVP: " + ", ".join(svp_reasons)
                except Exception:
                    pass  # SVP is supplementary, never block a trade

            # ========================================
            # CONFIDENCE CHECK - Sníženo pro více obchodů
            # ========================================
            MIN_CONFIDENCE = 0.55  # Sníženo z 0.6 - více signálů projde
            confidence = result.get("confidence", 0)

            if signal in ["BUY", "SELL"] and confidence < MIN_CONFIDENCE:
                self.log(f"[{yf_ticker}] Low confidence ({confidence:.0%}), skipping")
                return False
            # ========================================
            
            # ========================================
            # SMART CHECK (New Feature)
            # ========================================
            # 1. Market Sentiment (Panic Check)
            is_safe, msg = self.smart_analyst.get_market_sentiment()
            if not is_safe:
                self.log(f"⚠️ Market Sentiment Unsafe: {msg}. Skipping trade.")
                return False
                
            # 2. Analyst Ratings (Yahoo Finance)
            # Only check for priority tickers or stocks to save API calls
            if "USD" not in yf_ticker and "=" not in yf_ticker: # Primarily for Stocks
                rating = self.smart_analyst.get_analyst_rating(yf_ticker)
                score = rating.get('score', 0)
                rec = rating.get('recommendation', 'none')
                
                # VETO if analysts say SELL
                if score < -0.5: # Sell/Strong Sell
                    self.log(f"🚫 Analyst VETO for {yf_ticker}: {rec} (Score {score})")
                    return False
                
                # BOOST confidence if Strong Buy
                if score > 0.8:
                    self.log(f"⭐ Analyst STRONG BUY for {yf_ticker}")
            # ========================================

            if signal in ["BUY", "SELL"]:
                # ========================================
                # DIRECTION-AWARE COOLDOWN CHECK
                # Povolí opačný směr i během cooldownu (hedging)
                # ========================================
                last_trade_info = self.last_trade_times.get(yf_ticker)
                if last_trade_info:
                    last_time, last_direction = last_trade_info if isinstance(last_trade_info, tuple) else (last_trade_info, None)
                    
                    if time.time() - last_time < 900:  # 15 min cooldown
                        if last_direction == signal:
                            # Stejný směr během cooldownu = SKIP
                            remaining = int((900 - (time.time() - last_time)) / 60)
                            self.log(f"[{yf_ticker}] Cooldown: {remaining}min (same direction {signal})")
                            return False
                        else:
                            # Opačný směr = POVOLENO (hedging)
                            self.log(f"[{yf_ticker}] ✅ Hedge povoleno: {last_direction} → {signal}")
                # ========================================

                # Auto-toggle shorts based on learning
                if signal == "SELL" and not getattr(self, "enable_shorts", False):
                    self.log(f"[{yf_ticker}] SHORT disabled by learning engine, skipping")
                    return False

                # Check Limit
                positions = self.client.get_positions()
                max_pos = getattr(self, 'max_positions', MAX_POSITIONS)
                if len(positions) >= max_pos:
                    self.log(f"[LIMIT] Max positions ({max_pos}) reached. Skipping {t212_ticker}.")
                    return False
                
                # ========================================
                # CORRELATION CHECK (Risk Management)
                # ========================================
                corr_ok, corr_msg = self.check_correlation(t212_ticker, confidence, positions)
                if not corr_ok:
                    self.log(f"[SKIP] {corr_msg}")
                    return False
                
                if not corr_ok:
                    self.log(f"[SKIP] {corr_msg}")
                    return False
                
                # ========================================
                # NEWS FILTER (Safety)
                # ========================================
                news_ok, news_msg = self.check_news_filter(t212_ticker)
                if not news_ok:
                    self.log(f"[SKIP] 🚫 {news_msg}")
                    return False

                # ========================================
                # SMART SIZING (Growth)
                # ========================================
                # Default Risk
                risk_pct = getattr(self, 'max_risk_pct', SL_PCT)
                
                # Get Stats (Try Epic first as that's what Capital records)
                stats = self.learning_engine.ticker_stats.get(t212_ticker) or \
                        self.learning_engine.ticker_stats.get(yf_ticker, {})
                cons_loss = stats.get('consecutive_losses', 0)
                pf = stats.get('profit_factor', 0)
                trades_cnt = stats.get('trades', 0)
                
                # Logic:
                if cons_loss >= 2:
                    risk_pct *= 0.5 # Half size on losing streak
                    self.log(f"📉 Sizing: Reduced risk to {risk_pct*100:.2f}% (Loss Streak)")
                elif pf > 2.0 and trades_cnt >= 5 and cons_loss == 0:
                    risk_pct *= 1.4 # Boost 40% (approx 1.0% risk)
                    self.log(f"🚀 Sizing: Boosted risk to {risk_pct*100:.2f}% (High Performance)")
                
                # Update Trade Amount for this trade ONLY
                # self.trade_amount_czk = ... we use self.trade_amount (CZK/USD?)
                # We need to calculate position size based on SL distance and Risk Amount
                # BUT current logic uses fixed "trade_amount" (Margin).
                # We will adjust "trade_amount" directly.
                
                adjusted_trade_amount = self.trade_amount
                if risk_pct != SL_PCT:
                    # Scale trade amount relative to base risk (0.7% or 1%)
                    # multiplier = risk_pct / SL_PCT
                    # adjusted_trade_amount = self.trade_amount * multiplier 
                    # Simpler: Just override if we had dynamic calculation, but we use fixed amount.
                    # Let's assume trade_amount is the MARGIN we put in.
                    # If we reduce risk, we put less margin? 
                    # NO, risk management means Position Size = (Account * Risk%) / SL_Dist.
                    # Current bot uses Fixed Trade Amount (Margin).
                    # So we should scale the Margin Amount.
                    scaler = risk_pct / SL_PCT
                    adjusted_trade_amount = self.trade_amount * scaler

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

                    # Get protection levels from strategy
                    stop_price = result.get("sl")
                    limit_price = result.get("tp")

                    # === RISK-BASED POSITION SIZING (v3.1 FIX) ===
                    # Calculate SL distance for risk-based sizing
                    if stop_price and last_price > 0:
                        sl_distance = abs(last_price - stop_price)
                    else:
                        # Fallback: use asset-class appropriate default
                        from elite_strategy import EliteStrategy
                        risk_profile = EliteStrategy.RISK_PROFILES.get(asset_class, EliteStrategy.RISK_PROFILES["default"])
                        sl_distance = last_price * risk_profile["min_sl_pct"]

                    if sl_distance <= 0:
                        self.log(f"⚠️ {t212_ticker}: Invalid SL distance, skipping")
                        return False

                    # Use risk-based sizing
                    qty = self.calculate_risk_based_size(t212_ticker, sl_distance, last_price, asset_class)
                    if qty <= 0:
                        self.log(f"❌ {t212_ticker}: Calculated QTY is 0 or negative! Skipping.")
                        return False

                    # === DETAILED TRADE LOGGING (v3.2) ===
                    sl_pct = sl_distance / last_price * 100
                    tp_distance = abs(last_price - limit_price) if limit_price else 0
                    tp_pct = tp_distance / last_price * 100 if last_price > 0 else 0
                    rr_actual = tp_distance / sl_distance if sl_distance > 0 else 0
                    atr_val = result.get('atr', 0)
                    confluence = result.get('confluence_score', 0)
                    risk_pct_now = self.get_current_risk_pct()

                    action_word = "Buying" if signal == "BUY" else "Shorting"
                    self.log(f"{'='*50}")
                    self.log(f"📊 TRADE #{getattr(self, '_total_live_trades', 0)+1} | {action_word} {qty} {t212_ticker} @ ${last_price:.4f}")
                    self.log(f"   Asset: {asset_class} | Confidence: {confidence:.0%} | Confluence: {confluence}/6")
                    self.log(f"   SL: {stop_price:.5f} ({sl_pct:.2f}%) | TP: {limit_price:.5f} ({tp_pct:.2f}%) | R:R {rr_actual:.1f}")
                    self.log(f"   Risk: {risk_pct_now*100:.1f}% equity | Reason: {reason}")
                    self.log(f"{'='*50}")

                    # === DRY-RUN MODE CHECK ===
                    # Effective Dry Run = Configured OR Startup Safety Phase
                    is_dry_run = self.dry_run
                    if self.startup_cycles < self.min_dry_run_cycles:
                         is_dry_run = True
                         self.log(f"🛡️ SAFETY MODE: Forcing DRY-RUN (Cycle {self.startup_cycles}/{self.min_dry_run_cycles})")

                    if is_dry_run:
                        self.log(f"🔵 DRY-RUN: Trade NOT executed — dry_run mode active")

                        if hasattr(self, 'telegram') and self.telegram.enabled:
                            self.telegram.send_message(
                                f"🔵 <b>DRY-RUN SIGNAL</b>\n\n"
                                f"<b>{signal}</b> {t212_ticker} @ ${last_price:.4f}\n"
                                f"SL: {stop_price:.5f} ({sl_pct:.2f}%)\n"
                                f"TP: {limit_price:.5f} ({tp_pct:.2f}%)\n"
                                f"R:R: {rr_actual:.1f} | {asset_class}\n"
                                f"Confluence: {confluence}/6"
                            )

                        self.last_trade_times[yf_ticker] = (time.time(), signal)
                        return True

                    try:
                        # Capital Client place_market_order(epic, size, direction, sl, tp)
                        order_result = self.client.place_market_order(
                            t212_ticker,
                            qty,
                            direction=signal,
                            stop_loss=stop_price,
                            take_profit=limit_price,
                            trailing_stop=False
                        )
                        
                        self.log(f"✅ {signal} Order CONFIRMED: {order_result.get('dealReference', 'OK')}")

                        # Store indicator metadata for learning engine
                        if not hasattr(self, '_trade_metadata'):
                            self._trade_metadata = {}
                        self._trade_metadata[t212_ticker] = {
                            'indicators_used': result.get('indicators_used', []),
                            'confluence_score': result.get('confluence_score', 0),
                            'strategy': result.get('strategy', strategy_used),
                            'regime': regime,
                            'asset_class': asset_class,
                            'sl_distance_pct': result.get('sl_distance_pct', 0),
                            'rr_ratio': result.get('rr_ratio', 0),
                        }

                        # 📲 TELEGRAM NOTIFICATION
                        if hasattr(self, 'telegram') and self.telegram.enabled:
                            self.telegram.notify_trade(
                                direction=signal,
                                ticker=t212_ticker,
                                qty=qty,
                                price=last_price,
                                sl=stop_price,
                                tp=limit_price
                            )

                        self.last_trade_times[yf_ticker] = (time.time(), signal)  # Uložit směr
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
                        self.last_trade_times[yf_ticker] = (time.time(), signal)  # Uložit směr
                        return True
                    except Exception as e:
                        self.log(f"Order failed: {e}")
                        return False
        except Exception as e:
            self.log(f"⚠️ Error scanning {yf_ticker}: {e}")
        return False

    def record_closed_trades(self):
        """Check for closed trades and record them in learning engine."""
        if self.broker != "capital" or not hasattr(self, 'learning_engine'):
            return
        
        try:
            # Track which trades we've already recorded
            if not hasattr(self, '_recorded_trade_ids'):
                self._recorded_trade_ids = set()
            
            # Get recent history
            history = self.client.get_history(last_hours=24)
            
            for trade in (history or []):
                trade_id = trade.get('reference') or trade.get('dealId') or str(trade.get('date', ''))
                
                # Skip if already recorded
                if trade_id in self._recorded_trade_ids:
                    continue
                
                pnl = trade.get('profitAndLoss')
                if pnl is None or pnl == 0:
                    continue
                
                epic = trade.get('epic') or trade.get('instrumentName', 'UNKNOWN')
                direction = trade.get('direction', 'BUY')

                # Retrieve indicator metadata stored at trade open
                meta = getattr(self, '_trade_metadata', {}).get(epic, {})

                # Record in learning engine (with indicator combo + asset class tracking)
                self.learning_engine.record_trade(
                    ticker=epic,
                    pnl=float(pnl),
                    direction=direction,
                    entry_price=float(trade.get('openLevel', 0)),
                    exit_price=float(trade.get('closeLevel', 0)),
                    exit_reason="TP" if float(pnl) > 0 else "SL",
                    indicators_used=meta.get('indicators_used', []),
                    asset_class=meta.get('asset_class', self.detect_asset_class(epic)),
                )
                
                self._recorded_trade_ids.add(trade_id)
                
                # Keep set from growing too large
                if len(self._recorded_trade_ids) > 1000:
                    self._recorded_trade_ids = set(list(self._recorded_trade_ids)[-500:])
                    
        except Exception as e:
            # Silent fail - don't disrupt main loop
            pass
    
    def optimize_learning(self):
        """Run periodic optimization (call once per day or on startup)."""
        if hasattr(self, 'learning_engine'):
            self.learning_engine.optimize_params()
            
            # Update strategy with new learned params
            learned = self.learning_engine.get_learned_params()
            
            # Re-merge with base config (same logic as __init__)
            base_config = self.strategy_config.copy()
            if "rsi_oversold" in learned: base_config["rsi_oversold"] = learned["rsi_oversold"]
            if "rsi_overbought" in learned: base_config["rsi_overbought"] = learned["rsi_overbought"]
            if "atr_sl_mult" in learned: base_config["atr_sl_mult"] = learned["atr_sl_mult"]
            base_config["min_rr_ratio"] = learned.get("min_rr_ratio", 1.0)

            # Hardforce some High Volume settings if aggressive mode is ON (same as init)
            if self.aggressive_mode:
                 # MATCH __init__: RSI 40/60, min_rr 2.0 (2026 guide)
                 base_config["rsi_oversold"] = 40
                 base_config["rsi_overbought"] = 60
                 base_config["min_rr_ratio"] = 2.0
                 self.enable_shorts = True

            # Update existing hybrid strategy's mean reversion component
            self.hybrid_strategy.mean_reversion = MeanReversionStrategy({
                "rsi_oversold": base_config.get("rsi_oversold", 40),
                "rsi_overbought": base_config.get("rsi_overbought", 60),
                "atr_sl_mult": base_config.get("atr_sl_mult", 2.0),
                "min_rr_ratio": 1.5,  # Mean reversion can use 1.5 (trend uses 2.0)
                "use_trend_filter": False,
                "use_volatility_filter": True,
                "use_volume_filter": False,
                "use_session_filter": False,
            })
            self.mean_reversion = self.hybrid_strategy.mean_reversion  # Update alias
            if not self.aggressive_mode:
                self.enable_shorts = learned.get("enable_shorts", self.strategy_config.get("enable_shorts", False))
            
            self.log(f"🧠 Strategy updated with learned params: RSI {self.mean_reversion.rsi_oversold}/{self.mean_reversion.rsi_overbought}")

    def check_correlation(self, new_ticker, confidence=0.0, positions=None):
        """
        Check if we are already exposed to currencies in the new ticker.
        Returns: (passed: bool, reason: str)
        """
        if self.broker != "capital": return True, "" # Only implementing for Forex/Capital for now
        
        # Extract currencies from new ticker (e.g. "GBPUSD" -> ["GBP", "USD"])
        # Simple heuristic: 6 chars = currency pair
        if len(new_ticker) != 6 and not "=" in new_ticker:
            return True, "" # Probably Stock/Index - ignore
            
        # Clean ticker
        clean_new = new_ticker.split('=')[0]
        if len(clean_new) != 6: return True, ""
        
        new_curr_1 = clean_new[:3]
        new_curr_2 = clean_new[3:]
        
        # Get open positions
        if positions is None:
            try:
                positions = self.client.get_positions()
            except:
                return True, "" # API fail -> permissive
            
        for pos in positions:
            epic = pos.get('epic', '')
            # Extract currencies from open position
            # Capital epics are like "GBPUSD"
            if len(epic) == 6 or (len(epic) > 6 and epic[6:] == "USD"): # Handle basic pairs
                 # Simplified extraction
                 existing_curr_1 = epic[:3]
                 existing_curr_2 = epic[3:6]
                 
                 # Check Overlap
                 # If ANY currency matches, we have exposure
                 # EXCEPTION: High confidence (>90%) -> Allow stacking
                 if confidence < 0.90:
                     if new_curr_1 in [existing_curr_1, existing_curr_2] or \
                        new_curr_2 in [existing_curr_1, existing_curr_2]:
                         return False, f"Correlation Conflict: Exposed to {new_curr_1} or {new_curr_2} via {epic}"
                         
        return True, ""

    def check_news_filter(self, ticker):
        """
        Check if High Impact news is imminent for the ticker's currencies.
        Returns: (passed: bool, reason: str)
        """
        if self.broker != "capital": return True, ""
        
        # 1. Cache Check (Update every 60 mins)
        now = datetime.now()
        if not hasattr(self, "news_cache") or (now - self.news_cache_time).total_seconds() > 3600:
             self.log("Fetching Economic Calendar...")
             self.news_cache = get_economic_calendar()
             self.news_cache_time = now
        
        if self.news_cache.empty:
            return True, ""
            
        # 2. Extract Currencies
        if len(ticker) != 6 and "=" not in ticker: return True, ""
        clean = ticker.split('=')[0]
        currs = [clean[:3], clean[3:]] if len(clean) == 6 else ["USD"]
        
        # 3. Filter Events
        # Time format in DF is "HH:MM" (e.g. "14:30")
        try:
            current_hm = now.strftime("%H:%M")
            current_min = now.hour * 60 + now.minute
            
            for index, row in self.news_cache.iterrows():
                # Filter by Impact & Currency
                if row['Impact'] != 'High': continue
                if row['Country'] not in currs and row['Country'] != 'ALL': continue
                
                # Check Time
                event_time_str = row['Time']
                try:
                    eh, em = map(int, event_time_str.split(':'))
                    event_min = eh * 60 + em
                    
                    diff = abs(event_min - current_min)
                    if diff <= 30: # 30 min window
                        return False, f"News Event: {row['Event']} ({row['Country']}) at {event_time_str}"
                except:
                    continue
        except Exception as e:
             self.log(f"News Filter Error: {e}")
             
        return True, ""

    def scan_cycle(self):
        self.update_daily_pnl()
        self.startup_cycles += 1 # Increment safety counter

        # Record closed trades for learning (every cycle)
        self.record_closed_trades()

        # === v5.0: DAILY P&L LOGGING ===
        daily_pnl = getattr(self, 'daily_pnl', 0)
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
        self.log(f"{pnl_emoji} Denní P&L: {daily_pnl:+.2f} CZK | Cíl: +{self.daily_profit_target:.0f} | Limit: -{self.max_daily_loss:.0f}")

        # === v3.2: AUTO-PAUSE CHECK ===
        if getattr(self, '_auto_paused', False):
            self.log(f"🛑 AUTO-PAUSED: {self._consecutive_losses} consecutive losses. Resume manually.")
            return

        # === v3.2: DRAWDOWN CHECK ===
        dd_ok, dd_msg = self.check_drawdown_protection()
        if not dd_ok:
            self.log(f"🛑 {dd_msg}")
            self.session_stopped_reason = "drawdown"
            return

        if self.session_stopped_reason == "daily_loss":
            self.log(f"🛑 Denní P&L: {daily_pnl:+.2f} CZK — DAILY LOSS LIMIT hit (-{self.max_daily_loss:.0f}). Stop na den.")
            return
        if self.session_stopped_reason == "profit_target":
            self.log(f"✅ Denní P&L: {daily_pnl:+.2f} CZK — PROFIT TARGET dosažen (+{self.daily_profit_target:.0f}). Stop na den!")
            return
        if self.session_stopped_reason == "drawdown":
            self.log(f"🛑 Emergency drawdown stop active.")
            return

        if not self.open_instruments:
            self.get_open_markets()
        if not self.open_instruments:
            self.log("No markets open.")
            return

        subset = self.open_instruments
        if len(subset) > MAX_SCAN_PER_CYCLE:
             subset = random.sample(self.open_instruments, MAX_SCAN_PER_CYCLE)

        risk_pct = self.get_current_risk_pct()
        mode_str = "DRY-RUN" if self.dry_run else "LIVE"
        self.log(f"Scanning {len(subset)} assets [{mode_str} | Risk: {risk_pct*100:.1f}% | Trade #{getattr(self, '_total_live_trades', 0)+1}]")

        for i, item in enumerate(subset):
            if not self.is_running:
                break
            self.process_instrument(item)
            time.sleep(1)



    def monitor_positions(self):
        """
        v5.0: Aggressive position management for daily profit guarantee.

        Partial Close Schedule:
        - At 1.0R: Close 60% (lock quick profit EARLY)
        - At 1.5R: Close 50% of remaining
        - Rest trails aggressively

        Trailing Stop:
        - At 0.5R: Move SL to breakeven (EARLIER than before)
        - At 1.0R: Lock 0.3R profit
        - At 1.5R: Lock 0.8R profit
        - At 2.0R+: Lock 1.2R profit
        """
        if self.broker != "capital":
            return

        try:
            positions = self.client.get_positions()
            if not positions: return

            # Track partial close stages per deal
            if not hasattr(self, '_partial_stages'):
                self._partial_stages = {}  # deal_id -> set of completed stages

            for pos in positions:
                try:
                    market = pos.get('market', {})
                    pos_data = pos.get('position', {})

                    epic = market.get('epic') or pos.get('epic')
                    direction = pos_data.get('direction') or pos.get('direction')
                    entry_level = pos_data.get('level') or pos.get('level')
                    current_sl = pos_data.get('stopLevel') or pos.get('stopLevel')
                    deal_id = pos_data.get('dealId') or pos.get('dealId')
                    current_size = pos_data.get('size') or pos.get('size', 0)

                    if not epic or not deal_id or not entry_level:
                        continue

                    # Fetch live price
                    price_info = self.client.get_prices(epic)
                    snapshot = price_info.get('snapshot', {})
                    bid = snapshot.get('bid')
                    offer = snapshot.get('offer')

                    if not bid or not offer: continue

                    current_price = bid if direction == "BUY" else offer

                    # Calculate Profit Distance
                    if direction == "BUY":
                        profit_dist = current_price - entry_level
                        risk_dist = entry_level - current_sl if current_sl else entry_level * 0.01
                    else:
                        profit_dist = entry_level - current_price
                        risk_dist = current_sl - entry_level if current_sl else entry_level * 0.01

                    one_r = abs(risk_dist) if risk_dist > 0 else entry_level * 0.01

                    # Initialize partial stage tracker
                    if deal_id not in self._partial_stages:
                        self._partial_stages[deal_id] = set()
                    stages_done = self._partial_stages[deal_id]

                    # === TIERED PARTIAL CLOSES (v5.0 — AGGRESSIVE EARLY LOCK) ===
                    # Stage 1: At 1.0R -> Close 60% (lock profit FAST)
                    if profit_dist >= (one_r * 1.0) and 'P1' not in stages_done:
                        partial_size = round(current_size * 0.60, 2)
                        if partial_size > 0:
                            self.log(f"💰 PARTIAL-1: {epic} @ 1.0R — closing 60% ({partial_size})")
                            result = self.client.reduce_position(deal_id, partial_size)
                            if result:
                                stages_done.add('P1')
                                if hasattr(self, 'telegram') and self.telegram.enabled:
                                    pnl_est = partial_size * profit_dist
                                    self.telegram.notify_close(epic, pnl_est, "Partial-1 @ 1.0R (60%)")

                    # Stage 2: At 1.5R -> Close 50% of REMAINING
                    elif profit_dist >= (one_r * 1.5) and 'P2' not in stages_done and 'P1' in stages_done:
                        partial_size = round(current_size * 0.50, 2)  # 50% of remaining ≈ 20% original
                        if partial_size > 0:
                            self.log(f"💰 PARTIAL-2: {epic} @ 1.5R — closing 50% remaining ({partial_size})")
                            result = self.client.reduce_position(deal_id, partial_size)
                            if result:
                                stages_done.add('P2')
                                if hasattr(self, 'telegram') and self.telegram.enabled:
                                    pnl_est = partial_size * profit_dist
                                    self.telegram.notify_close(epic, pnl_est, "Partial-2 @ 1.5R")

                    # === ADAPTIVE TRAILING STOP (v3.2) ===
                    new_sl = None
                    reason = ""

                    def get_lock_sl(r_mult):
                        if direction == "BUY":
                            return entry_level + (one_r * r_mult)
                        else:
                            return entry_level - (one_r * r_mult)

                    def sl_should_update(desired):
                        if direction == "BUY":
                            return current_sl is None or current_sl < desired
                        else:
                            return current_sl is None or current_sl > desired

                    # === ADAPTIVE TRAILING (v5.0 — AGGRESSIVE PROFIT LOCK) ===
                    # Level 4: Profit > 2.0R -> Lock 1.2R
                    if profit_dist > (one_r * 2.0):
                        desired = get_lock_sl(1.2)
                        if sl_should_update(desired):
                            new_sl = desired
                            reason = "Trail L4: Lock 1.2R"

                    # Level 3: Profit > 1.5R -> Lock 0.8R
                    elif profit_dist > (one_r * 1.5):
                        desired = get_lock_sl(0.8)
                        if sl_should_update(desired):
                            new_sl = desired
                            reason = "Trail L3: Lock 0.8R"

                    # Level 2: Profit > 1.0R -> Lock 0.3R
                    elif profit_dist > (one_r * 1.0):
                        desired = get_lock_sl(0.3)
                        if sl_should_update(desired):
                            new_sl = desired
                            reason = "Trail L2: Lock 0.3R"

                    # Level 1: Profit > 0.5R -> Breakeven (EARLIER)
                    elif profit_dist > (one_r * 0.5):
                        desired = entry_level
                        if sl_should_update(desired):
                            new_sl = desired
                            reason = "Trail L1: Breakeven @ 0.5R"

                    # Execute SL Update
                    if new_sl:
                        self.log(f"🛡️ {epic}: {reason} (SL -> {new_sl:.5f})")
                        success = self.client.update_position(deal_id, stop_level=new_sl)
                        if not success:
                            self.log(f"❌ Failed to update SL for {epic}")

                except Exception:
                    pass

            # Clean up old deal IDs from partial tracker
            active_deals = {(p.get('position', {}) or {}).get('dealId') for p in positions}
            stale = [d for d in self._partial_stages if d not in active_deals]
            for d in stale:
                del self._partial_stages[d]

        except Exception:
            pass
            
    def send_daily_report_if_needed(self):
        """Pošli denní report v 23:00 UTC."""
        from datetime import datetime
        
        now = datetime.utcnow()
        
        # Označ poslední report
        if not hasattr(self, '_last_daily_report'):
            self._last_daily_report = None
        
        # Report v 23:00 UTC (pouze jednou denně)
        if now.hour == 23 and self._last_daily_report != now.date():
            try:
                # Získej dnešní statistiky
                summary = self.learning_engine.get_stats_summary()
                
                total_trades = summary.get('total_trades', 0)
                wins = int(total_trades * summary.get('overall_win_rate', 0) / 100)
                losses = total_trades - wins
                pnl = summary.get('total_pnl', 0)
                
                # Získej balance
                acc = self.client.get_account_info()
                accounts = acc.get('accounts', [])
                balance = accounts[0].get('balance', {}).get('balance', 0) if accounts else 0
                
                if hasattr(self, 'telegram') and self.telegram.enabled:
                    self.telegram.send_daily_report(total_trades, wins, losses, pnl, balance)
                    self.log("📊 Daily report sent to Telegram")
                
                self._last_daily_report = now.date()
                
            except Exception as e:
                self.log(f"Daily report error: {e}")

    def start_loop(self):
        """Starts the main loop in a thread."""
        if self.is_running: return
        self.is_running = True
        self.log("Starting bot loop...")
        
        def run():
            try:
                self.initialize_data()
                last_monitor_time = 0
                while self.is_running:
                    self.update_cache() # Keep UI fresh
                    self.scan_cycle()
                    
                    # Faster loop for scalping monitors (e.g. 5s per check)
                    for _ in range(6): # 6 * 5s = 30s cycle
                        if not self.is_running: break
                        
                        # Monitor positions (Trailing Stop + Partial Profit)
                        if time.time() - last_monitor_time > 5:
                            self.monitor_positions()
                            self.send_daily_report_if_needed()  # Daily report v 23:00 UTC
                            last_monitor_time = time.time()
                            
                        time.sleep(5)
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
