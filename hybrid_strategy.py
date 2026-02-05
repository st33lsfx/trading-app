"""
Hybrid Adaptive Strategy v1.0
=============================
Automaticky přepíná mezi strategiemi podle tržního režimu:

RANGING (ADX < 25): Mean Reversion strategy
TRENDING (ADX >= 25): Trend Following strategy

Klíčové vlastnosti:
- Regime detection pomocí ADX
- Automatický strategy switching
- Unified risk management
- Performance tracking per regime
"""

import pandas as pd
import numpy as np
from datetime import datetime
from ta.trend import ADXIndicator

# Import existing strategies
from mean_reversion_strategy import MeanReversionStrategy
from trend_strategy import TrendStrategy


class HybridStrategy:
    """
    Hybridní adaptivní strategie pro 2026.
    Kombinuje mean reversion a trend following podle tržního režimu.
    """
    
    def __init__(self, config=None):
        self.config = config or {}
        
        # Regime detection thresholds
        self.adx_range_strong = 20    # ADX < 20 = silný ranging
        self.adx_range_weak = 25      # ADX 20-25 = slabý ranging
        self.adx_trend_weak = 35      # ADX 25-35 = slabý trend
        # ADX > 35 = silný trend
        
        # Initialize sub-strategies
        self.mean_reversion = MeanReversionStrategy(config)
        self.trend_following = TrendStrategy(config)
        
        # Performance tracking per regime
        self.regime_stats = {
            'RANGE_STRONG': {'trades': 0, 'wins': 0, 'pnl': 0},
            'RANGE_WEAK': {'trades': 0, 'wins': 0, 'pnl': 0},
            'TREND_WEAK': {'trades': 0, 'wins': 0, 'pnl': 0},
            'TREND_STRONG': {'trades': 0, 'wins': 0, 'pnl': 0},
        }
        
        # Current regime cache
        self.current_regime = None
        self.regime_history = []
    
    def detect_regime(self, df):
        """
        Detekuj aktuální tržní režim pomocí ADX.
        
        Returns:
            tuple: (regime_name, adx_value, confidence)
        """
        if len(df) < 20:
            return 'UNKNOWN', 0, 0
        
        # Calculate ADX if not present
        if 'adx' not in df.columns:
            adx_indicator = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
            adx = adx_indicator.adx().iloc[-1]
        else:
            adx = df['adx'].iloc[-1]
        
        if pd.isna(adx):
            return 'UNKNOWN', 0, 0
        
        # Determine regime
        if adx < self.adx_range_strong:
            regime = 'RANGE_STRONG'
            confidence = 0.8
        elif adx < self.adx_range_weak:
            regime = 'RANGE_WEAK'
            confidence = 0.6
        elif adx < self.adx_trend_weak:
            regime = 'TREND_WEAK'
            confidence = 0.6
        else:
            regime = 'TREND_STRONG'
            confidence = 0.8
        
        return regime, adx, confidence
    
    def select_strategy(self, regime):
        """
        Vyber správnou strategii podle režimu.
        
        Returns:
            tuple: (strategy_instance, strategy_name)
        """
        if regime in ['RANGE_STRONG', 'RANGE_WEAK']:
            return self.mean_reversion, 'MEAN_REVERSION'
        else:
            return self.trend_following, 'TREND_FOLLOWING'
    
    def get_signal(self, df, config=None, major_trend="NEUTRAL"):
        """
        Získej trading signál s automatickým přepínáním strategií.
        
        Returns:
            dict s klíči: signal, confidence, sl, tp, rsi, reason, filters, regime, strategy
        """
        if len(df) < 30:
            return {
                "signal": "NEUTRAL", 
                "confidence": 0, 
                "reason": "Nedostatek dat",
                "rsi": 50,
                "regime": "UNKNOWN",
                "strategy": "NONE"
            }
        
        # Detect current regime
        regime, adx, regime_confidence = self.detect_regime(df)
        self.current_regime = regime
        
        if regime == 'UNKNOWN':
            return {
                "signal": "NEUTRAL",
                "confidence": 0,
                "reason": "Cannot detect regime",
                "rsi": 50,
                "regime": regime,
                "strategy": "NONE"
            }
        
        # Select strategy based on regime
        strategy, strategy_name = self.select_strategy(regime)
        
        # Get signal from selected strategy
        signal_data = strategy.get_signal(df, config, major_trend)
        
        # Enhance result with regime info
        signal_data['regime'] = regime
        signal_data['regime_adx'] = adx
        signal_data['strategy'] = strategy_name
        
        # Adjust confidence based on regime
        if signal_data['signal'] != 'NEUTRAL':
            # Higher confidence in strong regimes
            if regime in ['RANGE_STRONG', 'TREND_STRONG']:
                signal_data['confidence'] = min(signal_data.get('confidence', 0.5) * 1.1, 1.0)
            
            # Add regime info to filters
            filters = signal_data.get('filters', [])
            filters.insert(0, f"📊 Regime: {regime} (ADX {adx:.1f})")
            filters.insert(1, f"🎯 Strategy: {strategy_name}")
            signal_data['filters'] = filters
        
        return signal_data
    
    def record_trade_result(self, regime, is_win, pnl):
        """Zaznamenej výsledek obchodu pro daný režim."""
        if regime in self.regime_stats:
            self.regime_stats[regime]['trades'] += 1
            if is_win:
                self.regime_stats[regime]['wins'] += 1
            self.regime_stats[regime]['pnl'] += pnl
    
    def get_regime_performance(self):
        """Získej performance statistiky per režim."""
        result = {}
        for regime, stats in self.regime_stats.items():
            trades = stats['trades']
            if trades > 0:
                win_rate = (stats['wins'] / trades) * 100
                result[regime] = {
                    'trades': trades,
                    'win_rate': win_rate,
                    'pnl': stats['pnl']
                }
        return result
    
    def get_current_regime(self):
        """Získej aktuální tržní režim."""
        return self.current_regime
    
    def get_regime_description(self, regime):
        """Získej popis režimu pro UI."""
        descriptions = {
            'RANGE_STRONG': '📊 Silný Ranging - ideální pro Mean Reversion',
            'RANGE_WEAK': '📊 Slabý Ranging - opatrná Mean Reversion',
            'TREND_WEAK': '📈 Slabý Trend - opatrný Trend Following',
            'TREND_STRONG': '📈 Silný Trend - agresivní Trend Following',
            'UNKNOWN': '❓ Neznámý režim'
        }
        return descriptions.get(regime, regime)


# Singleton instance
_hybrid_strategy = None

def get_hybrid_strategy(config=None):
    """Získej singleton instanci hybridní strategie."""
    global _hybrid_strategy
    if _hybrid_strategy is None:
        _hybrid_strategy = HybridStrategy(config)
    return _hybrid_strategy


if __name__ == "__main__":
    import yfinance as yf
    
    print("Testing Hybrid Strategy...")
    print("=" * 50)
    
    # Test on multiple tickers
    tickers = ["EURUSD=X", "BTC-USD", "AAPL"]
    
    strategy = HybridStrategy()
    
    for ticker in tickers:
        try:
            data = yf.download(ticker, period="1mo", interval="1h", progress=False)
            if len(data) < 30:
                continue
                
            signal = strategy.get_signal(data)
            
            print(f"\n{ticker}:")
            print(f"  Regime: {signal.get('regime', 'N/A')} (ADX: {signal.get('regime_adx', 0):.1f})")
            print(f"  Strategy: {signal.get('strategy', 'N/A')}")
            print(f"  Signal: {signal.get('signal', 'N/A')}")
            print(f"  Confidence: {signal.get('confidence', 0):.2f}")
            print(f"  Reason: {signal.get('reason', '')}")
        except Exception as e:
            print(f"\n{ticker}: Error - {e}")
    
    print("\n" + "=" * 50)
    print("Test complete!")
