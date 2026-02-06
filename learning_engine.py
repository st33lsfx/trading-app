"""
Self-Learning Trading Engine v2.0
=================================
Upgraded with:
- Faster optimization (every 10 trades)
- R:R tracking per trade
- Smart unblacklisting (7-day auto-retry)
- Full Supabase integration (primary storage)
- Version control for data schema
"""

import os
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict


class LearningEngine:
    """
    Self-learning module for trading bot.
    Tracks performance and auto-optimizes parameters.
    """
    
    VERSION = 2  # Data schema version
    OPTIMIZATION_INTERVAL = 10  # Optimize after every N trades
    BLACKLIST_RETRY_DAYS = 7  # Auto-retry blacklisted assets after N days
    
    def __init__(self, data_file="learning_data.json", use_supabase=True):
        self.data_file = data_file
        self.use_supabase = use_supabase
        self.supabase = None
        
        # Performance tracking
        self.ticker_stats = defaultdict(lambda: {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "last_trade": None,
            "consecutive_losses": 0,
            "auto_blacklisted": False,
            "blacklist_reason": None,
            "blacklist_date": None,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            # NEW v2.0
            "avg_rr": 0.0,
            "rr_history": [],
            "trade_history": [],
        })

        # Direction performance (BUY vs SELL)
        self.direction_stats = {
            "BUY": {"trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0},
            "SELL": {"trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0},
        }

        # Activity log
        self.activity_log = []

        # NEW v2.1: Indicator combo performance tracking
        self.indicator_combos = defaultdict(lambda: {
            "trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0
        })

        # Trade counter for optimization trigger
        self._trades_since_optimization = 0
        
        # Strategy parameters that can be learned
        self.learned_params = {
            "rsi_oversold": 38,
            "rsi_overbought": 62,
            "atr_sl_mult": 2.0,
            "min_confidence": 0.55,
            "enable_shorts": True,
            "min_rr_ratio": 2.0,  # 2026 guide: R:R 2.0 minimum
        }
        
        # Auto-blacklist thresholds
        self.blacklist_rules = {
            "min_trades_for_eval": 5,
            "max_consecutive_losses": 4,
            "min_win_rate": 35.0,
            "min_profit_factor": 0.7,
            "recovery_trades": 10,
        }
        
        # Initialize Supabase
        if use_supabase:
            self._init_supabase()
        
        # Load existing data (Supabase first, then local)
        self._load_data()
    
    def _get_supabase_creds(self):
        """Get Supabase credentials securely."""
        try:
            import streamlit as st
            return st.secrets.get("SUPABASE_URL"), st.secrets.get("SUPABASE_KEY")
        except:
            pass
        # Fallback to env vars
        return os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    
    def _init_supabase(self):
        """Initialize Supabase connection."""
        try:
            from supabase import create_client
            
            url, key = self._get_supabase_creds()
            
            if url and key:
                self.supabase = create_client(url, key)
                print("✅ Learning Engine v2.0: Supabase connected")
            else:
                print("⚠️ Learning Engine: Supabase credentials not found")
                self.use_supabase = False
        except ImportError:
            print("⚠️ Learning Engine: Supabase not installed")
            self.use_supabase = False
        except Exception as e:
            print(f"⚠️ Learning Engine: Supabase init error: {e}")
            self.use_supabase = False
    
    def _load_data(self):
        """Load learning data - Supabase first, then local fallback."""
        loaded = False
        
        # Try Supabase first
        if self.supabase:
            try:
                result = self.supabase.table("bot_learning").select("*").eq("id", 1).execute()
                if result.data and len(result.data) > 0:
                    data = result.data[0].get("data", {})
                    self._parse_loaded_data(data)
                    print(f"✅ Learning Engine: Loaded from Supabase ({len(self.ticker_stats)} tickers)")
                    loaded = True
            except Exception as e:
                print(f"⚠️ Supabase load failed: {e}")
        
        # Fallback to local file
        if not loaded:
            self._load_from_file()
    
    def _load_from_file(self):
        """Load data from local JSON file."""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                self._parse_loaded_data(data)
                print(f"✅ Learning Engine: Loaded from local file ({len(self.ticker_stats)} tickers)")
        except Exception as e:
            print(f"⚠️ Learning Engine: Could not load local data: {e}")
    
    def _parse_loaded_data(self, data):
        """Parse loaded data into instance variables."""
        # Convert to defaultdict
        for ticker, stats in data.get("ticker_stats", {}).items():
            self.ticker_stats[ticker].update(stats)

        self.learned_params.update(data.get("learned_params", {}))
        self.direction_stats.update(data.get("direction_stats", {}))
        self.activity_log = data.get("activity_log", [])[-300:]

        # Load indicator combo stats (v2.1)
        for combo, stats in data.get("indicator_combos", {}).items():
            self.indicator_combos[combo].update(stats)
    
    def _save_data(self):
        """Save learning data to Supabase and local file."""
        data = {
            "version": self.VERSION,
            "ticker_stats": dict(self.ticker_stats),
            "learned_params": self.learned_params,
            "direction_stats": self.direction_stats,
            "indicator_combos": dict(self.indicator_combos),
            "activity_log": self.activity_log[-300:],
            "last_updated": datetime.utcnow().isoformat()
        }
        
        # Save locally first (always)
        try:
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Local save error: {e}")
        
        # Save to Supabase
        if self.supabase:
            try:
                self.supabase.table("bot_learning").upsert({
                    "id": 1,
                    "data": data,
                    "updated_at": datetime.utcnow().isoformat()
                }).execute()
            except Exception as e:
                print(f"⚠️ Supabase save error: {e}")
    
    def record_trade(self, ticker: str, pnl: float, direction: str,
                     entry_price: float, exit_price: float, exit_reason: str,
                     target_rr: float = None, achieved_rr: float = None,
                     volatility_atr: float = None, indicators_used: list = None):
        """
        Record a completed trade for learning.
        
        Args:
            ticker: Trading instrument (e.g., "GBPUSD")
            pnl: Profit/loss in account currency
            direction: "BUY" or "SELL"
            entry_price: Entry price
            exit_price: Exit price
            exit_reason: "TP", "SL", "Manual", "Trailing", etc.
            target_rr: Target R:R at entry (optional)
            achieved_rr: Actual R:R achieved (optional)
            volatility_atr: ATR at entry (optional)
        """
        stats = self.ticker_stats[ticker]
        
        stats["trades"] += 1
        stats["total_pnl"] += pnl
        stats["last_trade"] = datetime.utcnow().isoformat()
        
        if pnl > 0:
            stats["wins"] += 1
            stats["consecutive_losses"] = 0
            stats["gross_profit"] += pnl
        else:
            stats["losses"] += 1
            stats["consecutive_losses"] += 1
            stats["gross_loss"] += abs(pnl)

        # Update direction stats
        direction = direction.upper()
        if direction not in self.direction_stats:
            self.direction_stats[direction] = {"trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0}
        dir_stats = self.direction_stats[direction]
        # Ensure all keys exist (for legacy data)
        for key in ["trades", "wins", "losses", "total_pnl"]:
            if key not in dir_stats:
                dir_stats[key] = 0 if key != "total_pnl" else 0.0
        dir_stats["trades"] += 1
        dir_stats["total_pnl"] += pnl
        if pnl > 0:
            dir_stats["wins"] += 1
        else:
            dir_stats["losses"] += 1
        
        # Calculate metrics
        if stats["trades"] > 0:
            stats["win_rate"] = (stats["wins"] / stats["trades"]) * 100
        
        if stats["gross_loss"] > 0:
            stats["profit_factor"] = stats["gross_profit"] / stats["gross_loss"]
        else:
            stats["profit_factor"] = 999.0 if stats["gross_profit"] > 0 else 0.0
        
        # Track R:R (v2.0)
        if achieved_rr is not None:
            if "rr_history" not in stats:
                stats["rr_history"] = []
            stats["rr_history"].append(achieved_rr)
            # Keep last 50
            if len(stats["rr_history"]) > 50:
                stats["rr_history"] = stats["rr_history"][-50:]
            # Calculate average
            stats["avg_rr"] = sum(stats["rr_history"]) / len(stats["rr_history"])
        
        # Store trade history (v2.0)
        if "trade_history" not in stats:
            stats["trade_history"] = []
        stats["trade_history"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "exit_reason": exit_reason,
            "target_rr": target_rr,
            "achieved_rr": achieved_rr,
            "volatility_atr": volatility_atr
        })
        # Keep last 100
        if len(stats["trade_history"]) > 100:
            stats["trade_history"] = stats["trade_history"][-100:]
        
        # Track indicator combo performance (v2.1)
        if indicators_used:
            combo_key = "+".join(sorted(indicators_used))
            combo = self.indicator_combos[combo_key]
            combo["trades"] += 1
            combo["total_pnl"] += pnl
            if pnl > 0:
                combo["wins"] += 1
            else:
                combo["losses"] += 1

        # Check for auto-blacklist
        self._evaluate_ticker(ticker)

        # Check for smart unblacklist
        self._reevaluate_blacklist()

        # Activity log
        self._log_activity("trade", f"{ticker} {direction} PnL ${pnl:+.2f}")
        
        # Increment trade counter
        self._trades_since_optimization += 1
        
        # Auto-optimize if threshold reached
        if self._trades_since_optimization >= self.OPTIMIZATION_INTERVAL:
            self.optimize_params()
            self._trades_since_optimization = 0
        
        # Save data
        self._save_data()
        
        # Log
        emoji = "✅" if pnl > 0 else "❌"
        rr_str = f" R:R {achieved_rr:.2f}" if achieved_rr else ""
        print(f"📊 Learning: {emoji} {ticker} {direction} PnL: ${pnl:.2f}{rr_str} | "
              f"WR: {stats['win_rate']:.0f}% | PF: {stats['profit_factor']:.2f}")
    
    def _log_activity(self, event_type: str, message: str):
        """Append to activity log."""
        self.activity_log.append({
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            "type": event_type,
            "message": message
        })
        if len(self.activity_log) > 300:
            self.activity_log = self.activity_log[-300:]

    
    def set_protected_tickers(self, tickers: list):
        """Set list of protected tickers that are harder to blacklist."""
        self.protected_tickers = set(tickers)
        print(f"🛡️ Protected Tickers: {len(self.protected_tickers)} assets")

    def _evaluate_ticker(self, ticker: str):
        """Evaluate if ticker should be auto-blacklisted."""
        stats = self.ticker_stats[ticker]
        rules = self.blacklist_rules.copy()
        
        # Protected Ticker Logic
        if hasattr(self, 'protected_tickers') and ticker in self.protected_tickers:
            # Much looser rules for Elite Assets
            rules["max_consecutive_losses"] = 8  # Allow more drawdown
            rules["min_win_rate"] = 25.0         # Allow bad streak
            rules["min_profit_factor"] = 0.4
            
        if stats["trades"] < rules["min_trades_for_eval"]:
            return
        
        reasons = []
        
        if stats["consecutive_losses"] >= rules["max_consecutive_losses"]:
            reasons.append(f"{stats['consecutive_losses']} consecutive losses")
        
        if stats["win_rate"] < rules["min_win_rate"]:
            reasons.append(f"Win rate {stats['win_rate']:.0f}% < {rules['min_win_rate']}%")
        
        if stats["profit_factor"] < rules["min_profit_factor"]:
            reasons.append(f"Profit factor {stats['profit_factor']:.2f} < {rules['min_profit_factor']}")
        
        if reasons:
            stats["auto_blacklisted"] = True
            stats["blacklist_reason"] = "; ".join(reasons)
            stats["blacklist_date"] = datetime.utcnow().isoformat()
            self._log_activity("blacklist", f"{ticker}: {stats['blacklist_reason']}")
            print(f"🚫 AUTO-BLACKLIST: {ticker} - {stats['blacklist_reason']}")
    
    def _reevaluate_blacklist(self):
        """Smart unblacklisting - retry after N days."""
        now = datetime.utcnow()
        
        for ticker, stats in self.ticker_stats.items():
            if not stats.get("auto_blacklisted"):
                continue
            
            blacklist_date = stats.get("blacklist_date")
            if not blacklist_date:
                continue
            
            try:
                bl_date = datetime.fromisoformat(blacklist_date)
                days_since = (now - bl_date).days
                
                # Faster retry for Protected Tickers
                retry_days = self.BLACKLIST_RETRY_DAYS
                if hasattr(self, 'protected_tickers') and ticker in self.protected_tickers:
                    retry_days = 2 # Retry after 2 days for Elite assets
                
                if days_since >= retry_days:
                    # Reset for probation
                    stats["auto_blacklisted"] = False
                    stats["blacklist_reason"] = None
                    stats["blacklist_date"] = None
                    stats["consecutive_losses"] = 0
                    # Mark as probation (will be evaluated with fewer trades)
                    stats["probation"] = True
                    stats["probation_trades"] = 0
                    self._log_activity("unblacklist", f"{ticker}: Auto-retry after {days_since} days")
                    print(f"🔄 UNBLACKLIST: {ticker} - Auto-retry after {days_since} days")
            except:
                pass
    
    def is_blacklisted(self, ticker: str) -> tuple:
        """Check if ticker is auto-blacklisted."""
        stats = self.ticker_stats.get(ticker, {})
        
        if stats.get("auto_blacklisted", False):
            return True, stats.get("blacklist_reason", "Poor performance")
        
        return False, ""
    
    def get_learned_params(self) -> dict:
        """Get current learned parameters."""
        return self.learned_params.copy()
    
    def optimize_params(self):
        """
        Analyze all ticker performance and optimize strategy parameters.
        Called automatically every OPTIMIZATION_INTERVAL trades.
        """
        if not self.ticker_stats:
            return
        
        total_trades = sum(s["trades"] for s in self.ticker_stats.values())
        total_wins = sum(s["wins"] for s in self.ticker_stats.values())
        total_pnl = sum(s["total_pnl"] for s in self.ticker_stats.values())
        
        if total_trades < 10:
            return
        
        overall_wr = (total_wins / total_trades) * 100
        
        print(f"\n{'='*50}")
        print(f"📊 LEARNING OPTIMIZATION (v2.0)")
        print(f"{'='*50}")
        print(f"Total trades: {total_trades}")
        print(f"Overall WR: {overall_wr:.1f}%")
        print(f"Total PnL: ${total_pnl:.2f}")
        
        # Adjust parameters based on performance
        if overall_wr < 40:
            self.learned_params["rsi_oversold"] = max(30, self.learned_params["rsi_oversold"] - 2)
            self.learned_params["min_confidence"] = min(0.8, self.learned_params["min_confidence"] + 0.05)
            print("⚙️ Adjusting: More selective entries")
        
        elif overall_wr > 60:
            self.learned_params["rsi_oversold"] = min(42, self.learned_params["rsi_oversold"] + 1)
            self.learned_params["min_confidence"] = max(0.5, self.learned_params["min_confidence"] - 0.02)
            print("⚙️ Adjusting: Slightly more aggressive entries")
        
        # Check if shorts are working
        short_stats = self._get_direction_stats("SELL")
        long_stats = self._get_direction_stats("BUY")
        
        if short_stats["trades"] >= 5:
            short_wr = short_stats["win_rate"]
            if short_wr < 35:
                self.learned_params["enable_shorts"] = False
                self._log_activity("params", f"SHORT disabled (WR {short_wr:.0f}%)")
                print("⚙️ Disabling SHORT trades (poor performance)")
            elif short_wr > 50 and not self.learned_params["enable_shorts"]:
                self.learned_params["enable_shorts"] = True
                self._log_activity("params", f"SHORT enabled (WR {short_wr:.0f}%)")
                print("⚙️ Re-enabling SHORT trades")

        if overall_wr < 40 or overall_wr > 60:
            self._log_activity("params", f"Optimization: WR={overall_wr:.0f}% → RSI={self.learned_params['rsi_oversold']}")
        
        print(f"\nUpdated params: {self.learned_params}")
        self._save_data()
    
    def _get_direction_stats(self, direction: str) -> dict:
        """Get aggregated stats for a direction (BUY/SELL)."""
        stats = self.direction_stats.get(direction.upper(), {"trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
        trades = stats.get("trades", 0)
        wins = stats.get("wins", 0)
        win_rate = (wins / trades) * 100 if trades > 0 else 0.0
        return {
            "trades": trades,
            "wins": wins,
            "losses": stats.get("losses", 0),
            "win_rate": win_rate,
            "total_pnl": stats.get("total_pnl", 0.0),
        }
    
    def get_best_indicator_combos(self, min_trades: int = 5) -> list:
        """Get best performing indicator combinations (v2.1)."""
        results = []
        for combo, stats in self.indicator_combos.items():
            trades = stats.get("trades", 0)
            if trades >= min_trades:
                wins = stats.get("wins", 0)
                wr = (wins / trades) * 100
                pf = stats.get("total_pnl", 0)
                results.append({
                    "combo": combo,
                    "trades": trades,
                    "win_rate": round(wr, 1),
                    "total_pnl": round(pf, 2),
                })
        return sorted(results, key=lambda x: x["win_rate"], reverse=True)

    def get_best_tickers(self, n: int = 5) -> list:
        """Get top N performing tickers."""
        valid_tickers = [
            (ticker, stats) 
            for ticker, stats in self.ticker_stats.items()
            if stats["trades"] >= 3 and not stats.get("auto_blacklisted", False)
        ]
        
        sorted_tickers = sorted(
            valid_tickers, 
            key=lambda x: x[1]["profit_factor"], 
            reverse=True
        )
        
        return [t[0] for t in sorted_tickers[:n]]
    
    def get_blacklisted_tickers(self) -> list:
        """Get all auto-blacklisted tickers."""
        return [
            ticker for ticker, stats in self.ticker_stats.items()
            if stats.get("auto_blacklisted", False)
        ]
    
    def get_stats_summary(self) -> dict:
        """Get summary of learning stats."""
        total_trades = sum(s["trades"] for s in self.ticker_stats.values())
        total_wins = sum(s["wins"] for s in self.ticker_stats.values())
        total_pnl = sum(s["total_pnl"] for s in self.ticker_stats.values())
        blacklisted = len(self.get_blacklisted_tickers())
        long_stats = self._get_direction_stats("BUY")
        short_stats = self._get_direction_stats("SELL")
        
        # Calculate average R:R across all tickers
        all_rr = []
        for stats in self.ticker_stats.values():
            all_rr.extend(stats.get("rr_history", []))
        avg_rr = sum(all_rr) / len(all_rr) if all_rr else 0.0
        
        return {
            "total_tickers_tracked": len(self.ticker_stats),
            "total_trades": total_trades,
            "overall_win_rate": (total_wins / total_trades * 100) if total_trades > 0 else 0,
            "total_pnl": total_pnl,
            "auto_blacklisted_count": blacklisted,
            "best_tickers": self.get_best_tickers(3),
            "long_stats": long_stats,
            "short_stats": short_stats,
            "learned_params": self.learned_params,
            "avg_rr_achieved": round(avg_rr, 2),
            "best_indicator_combos": self.get_best_indicator_combos(3),
            "version": self.VERSION,
        }
    
    def reset_ticker(self, ticker: str):
        """Reset stats for a ticker."""
        if ticker in self.ticker_stats:
            self.ticker_stats[ticker] = {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "last_trade": None,
                "consecutive_losses": 0,
                "auto_blacklisted": False,
                "blacklist_reason": None,
                "blacklist_date": None,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "avg_rr": 0.0,
                "rr_history": [],
                "trade_history": [],
            }
            self._save_data()
            print(f"🔄 Reset stats for {ticker}")


# Singleton instance
_learning_engine = None

def get_learning_engine(use_supabase=True) -> LearningEngine:
    """Get singleton learning engine instance."""
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = LearningEngine(use_supabase=use_supabase)
    return _learning_engine


# Test
if __name__ == "__main__":
    engine = LearningEngine(use_supabase=False)
    
    print("\n=== Simulating trades ===\n")
    
    trades = [
        ("GBPUSD", 2.50, "BUY", 1.2500, 1.2550, "TP", 1.8, 2.0),
        ("GBPUSD", 1.80, "BUY", 1.2510, 1.2540, "TP", 1.8, 1.5),
        ("GBPUSD", -1.20, "BUY", 1.2520, 1.2500, "SL", 1.8, -1.0),
        ("ETHUSD", -3.50, "SELL", 2500, 2520, "SL", 2.0, -0.8),
        ("ETHUSD", -2.80, "SELL", 2510, 2530, "SL", 2.0, -0.7),
        ("ETHUSD", 4.20, "SELL", 2550, 2510, "TP", 2.0, 2.1),
        ("AUDUSD", 1.20, "BUY", 0.6500, 0.6520, "TP", 1.8, 1.6),
    ]
    
    for ticker, pnl, direction, entry, exit, reason, target_rr, achieved_rr in trades:
        engine.record_trade(ticker, pnl, direction, entry, exit, reason, target_rr, achieved_rr)
    
    print("\n=== Summary ===\n")
    summary = engine.get_stats_summary()
    for key, value in summary.items():
        print(f"{key}: {value}")
