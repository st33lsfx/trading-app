"""
Self-Learning Trading Engine
=============================
Bot se učí z vlastních obchodů a automaticky:
- Přidává ztrátové tickery do blacklistu
- Upravuje parametry strategie
- Optimalizuje na základě výsledků
"""

import os
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict


class LearningEngine:
    """
    Self-learning modul pro trading bota.
    Sleduje výkon a automaticky optimalizuje.
    """
    
    def __init__(self, data_file="learning_data.json", use_supabase=False):
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
            "blacklist_reason": None
        })
        
        # Strategy parameters that can be learned
        self.learned_params = {
            "rsi_oversold": 38,
            "rsi_overbought": 62,
            "atr_sl_mult": 2.0,
            "min_confidence": 0.6,
            "enable_shorts": True,
        }
        
        # Auto-blacklist thresholds
        self.blacklist_rules = {
            "min_trades_for_eval": 5,      # Minimum trades before evaluation
            "max_consecutive_losses": 4,    # Auto-blacklist after N losses in a row
            "min_win_rate": 35.0,          # Below this = blacklist
            "min_profit_factor": 0.7,      # Below this = blacklist
            "recovery_trades": 10,          # Trades before reconsidering blacklist
        }
        
        # Load existing data
        self._load_data()
        
        # Initialize Supabase if enabled
        if use_supabase:
            self._init_supabase()
    
    def _init_supabase(self):
        """Initialize Supabase connection."""
        try:
            from supabase import create_client
            
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
            
            if url and key:
                self.supabase = create_client(url, key)
                print("✅ Learning Engine: Supabase connected")
            else:
                print("⚠️ Learning Engine: Supabase credentials not found, using local storage")
                self.use_supabase = False
        except ImportError:
            print("⚠️ Learning Engine: Supabase not installed, using local storage")
            self.use_supabase = False
    
    def _load_data(self):
        """Load learning data from file or Supabase."""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    
                # Convert to defaultdict
                for ticker, stats in data.get("ticker_stats", {}).items():
                    self.ticker_stats[ticker].update(stats)
                
                self.learned_params.update(data.get("learned_params", {}))
                print(f"✅ Learning Engine: Loaded data for {len(self.ticker_stats)} tickers")
        except Exception as e:
            print(f"⚠️ Learning Engine: Could not load data: {e}")
    
    def _save_data(self):
        """Save learning data to file and optionally Supabase."""
        try:
            data = {
                "ticker_stats": dict(self.ticker_stats),
                "learned_params": self.learned_params,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Save locally
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
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
                    
        except Exception as e:
            print(f"⚠️ Learning Engine: Could not save data: {e}")
    
    def record_trade(self, ticker: str, pnl: float, direction: str, 
                     entry_price: float, exit_price: float, exit_reason: str):
        """
        Record a completed trade for learning.
        
        Args:
            ticker: Trading instrument (e.g., "GBPUSD")
            pnl: Profit/loss in account currency
            direction: "BUY" or "SELL"
            entry_price: Entry price
            exit_price: Exit price
            exit_reason: "TP", "SL", "Manual", etc.
        """
        stats = self.ticker_stats[ticker]
        
        stats["trades"] += 1
        stats["total_pnl"] += pnl
        stats["last_trade"] = datetime.utcnow().isoformat()
        
        if pnl > 0:
            stats["wins"] += 1
            stats["consecutive_losses"] = 0
        else:
            stats["losses"] += 1
            stats["consecutive_losses"] += 1
        
        # Calculate metrics
        if stats["trades"] > 0:
            stats["win_rate"] = (stats["wins"] / stats["trades"]) * 100
        
        # Calculate profit factor
        # We need to track gross profit/loss separately
        if not "gross_profit" in stats:
            stats["gross_profit"] = 0.0
            stats["gross_loss"] = 0.0
        
        if pnl > 0:
            stats["gross_profit"] += pnl
        else:
            stats["gross_loss"] += abs(pnl)
        
        if stats["gross_loss"] > 0:
            stats["profit_factor"] = stats["gross_profit"] / stats["gross_loss"]
        else:
            stats["profit_factor"] = 999.0 if stats["gross_profit"] > 0 else 0.0
        
        # Check for auto-blacklist
        self._evaluate_ticker(ticker)
        
        # Save data
        self._save_data()
        
        # Log
        emoji = "✅" if pnl > 0 else "❌"
        print(f"📊 Learning: {emoji} {ticker} {direction} PnL: ${pnl:.2f} | "
              f"WR: {stats['win_rate']:.0f}% | PF: {stats['profit_factor']:.2f}")
    
    def _evaluate_ticker(self, ticker: str):
        """Evaluate if ticker should be auto-blacklisted."""
        stats = self.ticker_stats[ticker]
        rules = self.blacklist_rules
        
        # Not enough data yet
        if stats["trades"] < rules["min_trades_for_eval"]:
            return
        
        reasons = []
        
        # Check consecutive losses
        if stats["consecutive_losses"] >= rules["max_consecutive_losses"]:
            reasons.append(f"{stats['consecutive_losses']} consecutive losses")
        
        # Check win rate
        if stats["win_rate"] < rules["min_win_rate"]:
            reasons.append(f"Win rate {stats['win_rate']:.0f}% < {rules['min_win_rate']}%")
        
        # Check profit factor
        if stats["profit_factor"] < rules["min_profit_factor"]:
            reasons.append(f"Profit factor {stats['profit_factor']:.2f} < {rules['min_profit_factor']}")
        
        if reasons:
            stats["auto_blacklisted"] = True
            stats["blacklist_reason"] = "; ".join(reasons)
            print(f"🚫 AUTO-BLACKLIST: {ticker} - {stats['blacklist_reason']}")
    
    def is_blacklisted(self, ticker: str) -> tuple:
        """
        Check if ticker is auto-blacklisted.
        
        Returns:
            (is_blacklisted: bool, reason: str)
        """
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
        Called periodically (e.g., daily).
        """
        if not self.ticker_stats:
            return
        
        # Aggregate stats
        total_trades = sum(s["trades"] for s in self.ticker_stats.values())
        total_wins = sum(s["wins"] for s in self.ticker_stats.values())
        total_pnl = sum(s["total_pnl"] for s in self.ticker_stats.values())
        
        if total_trades < 20:
            print("📊 Learning: Not enough trades for optimization yet")
            return
        
        overall_wr = (total_wins / total_trades) * 100
        
        print(f"\n{'='*50}")
        print(f"📊 LEARNING OPTIMIZATION")
        print(f"{'='*50}")
        print(f"Total trades: {total_trades}")
        print(f"Overall WR: {overall_wr:.1f}%")
        print(f"Total PnL: ${total_pnl:.2f}")
        
        # Adjust parameters based on performance
        if overall_wr < 40:
            # Win rate too low - be more selective
            self.learned_params["rsi_oversold"] = max(30, self.learned_params["rsi_oversold"] - 2)
            self.learned_params["min_confidence"] = min(0.8, self.learned_params["min_confidence"] + 0.05)
            print("⚙️ Adjusting: More selective entries (lower RSI threshold)")
        
        elif overall_wr > 60:
            # Win rate good - can be slightly less selective for more trades
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
                print("⚙️ Disabling SHORT trades (poor performance)")
            elif short_wr > 50 and not self.learned_params["enable_shorts"]:
                self.learned_params["enable_shorts"] = True
                print("⚙️ Re-enabling SHORT trades (improved performance)")
        
        print(f"\nUpdated params: {self.learned_params}")
        self._save_data()
    
    def _get_direction_stats(self, direction: str) -> dict:
        """Get aggregated stats for a direction (BUY/SELL)."""
        # This would need trade-level tracking to work properly
        # For now, return placeholder
        return {"trades": 0, "win_rate": 50.0}
    
    def get_best_tickers(self, n: int = 5) -> list:
        """Get top N performing tickers."""
        valid_tickers = [
            (ticker, stats) 
            for ticker, stats in self.ticker_stats.items()
            if stats["trades"] >= 3 and not stats.get("auto_blacklisted", False)
        ]
        
        # Sort by profit factor
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
        
        return {
            "total_tickers_tracked": len(self.ticker_stats),
            "total_trades": total_trades,
            "overall_win_rate": (total_wins / total_trades * 100) if total_trades > 0 else 0,
            "total_pnl": total_pnl,
            "auto_blacklisted_count": blacklisted,
            "best_tickers": self.get_best_tickers(3),
            "learned_params": self.learned_params
        }
    
    def reset_ticker(self, ticker: str):
        """Reset stats for a ticker (remove from blacklist, clear history)."""
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
                "blacklist_reason": None
            }
            self._save_data()
            print(f"🔄 Reset stats for {ticker}")


# Singleton instance
_learning_engine = None

def get_learning_engine(use_supabase=False) -> LearningEngine:
    """Get singleton learning engine instance."""
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = LearningEngine(use_supabase=use_supabase)
    return _learning_engine


# Test
if __name__ == "__main__":
    engine = LearningEngine()
    
    # Simulate some trades
    print("\n=== Simulating trades ===\n")
    
    trades = [
        ("GBPUSD", 2.50, "BUY"),
        ("GBPUSD", 1.80, "BUY"),
        ("GBPUSD", -1.20, "BUY"),
        ("GBPUSD", 2.10, "BUY"),
        ("ETHUSD", -3.50, "BUY"),
        ("ETHUSD", -2.80, "BUY"),
        ("ETHUSD", -4.20, "BUY"),
        ("ETHUSD", -1.90, "BUY"),
        ("ETHUSD", -2.50, "BUY"),  # 5 losses in a row
        ("AUDUSD", 1.20, "BUY"),
        ("AUDUSD", -0.80, "BUY"),
        ("AUDUSD", 0.90, "BUY"),
    ]
    
    for ticker, pnl, direction in trades:
        engine.record_trade(ticker, pnl, direction, 1.0, 1.01, "TP" if pnl > 0 else "SL")
    
    print("\n=== Summary ===\n")
    summary = engine.get_stats_summary()
    for key, value in summary.items():
        print(f"{key}: {value}")
    
    print("\n=== Blacklisted tickers ===")
    for ticker in engine.get_blacklisted_tickers():
        stats = engine.ticker_stats[ticker]
        print(f"  🚫 {ticker}: {stats['blacklist_reason']}")
