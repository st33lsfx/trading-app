"""
Hybrid Adaptive Strategy v2.0 (2026)
=====================================
Automatically switches between strategies based on market regime:

RANGING (ADX < 25): Mean Reversion (BB + RSI + confirmation candle)
TRENDING (ADX >= 25): Trend Following 2026 (Supertrend + HMA + ADX + VWAP + MACD + Ichimoku)

Key features:
- ADX-based regime detection with 4 zones
- Automatic strategy switching
- Indicator metadata passthrough for learning engine
- Performance tracking per regime
"""

import pandas as pd
import numpy as np
from datetime import datetime
from ta.trend import ADXIndicator

from mean_reversion_strategy import MeanReversionStrategy
from mean_reversion_strategy import MeanReversionStrategy
from elite_strategy import EliteStrategy


class HybridStrategy:
    """
    Hybrid adaptive strategy for 2026 markets.
    Combines mean reversion (ranging) and elite trend following (trending).
    """

    def __init__(self, config=None):
        self.config = config or {}

        # Regime detection thresholds
        self.adx_range_strong = 20    # ADX < 20 = strong ranging
        self.adx_range_weak = 25      # ADX 20-25 = weak ranging / transition
        self.adx_trend_weak = 35      # ADX 25-35 = developing trend
        # ADX > 35 = strong trend

        # Initialize sub-strategies
        self.mean_reversion = MeanReversionStrategy(config)
        self.trend_following = EliteStrategy(config)

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
        Detect current market regime via ADX.
        Returns: (regime_name, adx_value, confidence)
        """
        if len(df) < 20:
            return 'UNKNOWN', 0, 0

        if 'adx' not in df.columns:
            adx_indicator = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
            adx = adx_indicator.adx().iloc[-1]
        else:
            adx = df['adx'].iloc[-1]

        if pd.isna(adx):
            return 'UNKNOWN', 0, 0

        if adx < self.adx_range_strong:
            return 'RANGE_STRONG', adx, 0.8
        elif adx < self.adx_range_weak:
            return 'RANGE_WEAK', adx, 0.6
        elif adx < self.adx_trend_weak:
            return 'TREND_WEAK', adx, 0.6
        else:
            return 'TREND_STRONG', adx, 0.8

    def select_strategy(self, regime):
        """Select strategy based on regime."""
        if regime in ['RANGE_STRONG', 'RANGE_WEAK']:
            return self.mean_reversion, 'MEAN_REVERSION'
        else:
            return self.trend_following, 'TREND_2026'

    def get_signal(self, df, config=None, major_trend="NEUTRAL"):
        """
        Get trading signal with automatic strategy switching.
        Passes through all metadata including indicators_used for learning.
        """
        if len(df) < 30:
            return {
                "signal": "NEUTRAL",
                "confidence": 0,
                "reason": "Insufficient data",
                "rsi": 50,
                "regime": "UNKNOWN",
                "strategy": "NONE"
            }

        # Detect current regime
        regime, adx, regime_confidence = self.detect_regime(df)
        self.current_regime = regime

        # Track regime history
        self.regime_history.append(regime)
        if len(self.regime_history) > 100:
            self.regime_history.pop(0)

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
        # Only override strategy name if not already set by the sub-strategy
        if 'strategy' not in signal_data or signal_data['strategy'] in [None, 'NONE']:
            signal_data['strategy'] = strategy_name

        # Adjust confidence based on regime strength
        if signal_data['signal'] != 'NEUTRAL':
            if regime in ['RANGE_STRONG', 'TREND_STRONG']:
                signal_data['confidence'] = min(
                    signal_data.get('confidence', 0.5) * 1.1, 1.0
                )

            # Add regime info to filters
            filters = signal_data.get('filters', [])
            filters.insert(0, f"📊 Regime: {regime} (ADX {adx:.1f})")
            filters.insert(1, f"🎯 Strategy: {signal_data['strategy']}")
            signal_data['filters'] = filters

        return signal_data

    def record_trade_result(self, regime, is_win, pnl):
        """Record trade result for regime performance tracking."""
        if regime in self.regime_stats:
            self.regime_stats[regime]['trades'] += 1
            if is_win:
                self.regime_stats[regime]['wins'] += 1
            self.regime_stats[regime]['pnl'] += pnl

    def get_regime_performance(self):
        """Get performance statistics per regime."""
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
        return self.current_regime

    def get_regime_description(self, regime):
        descriptions = {
            'RANGE_STRONG': '📊 Strong Ranging - Mean Reversion active',
            'RANGE_WEAK': '📊 Weak Ranging - Cautious Mean Reversion',
            'TREND_WEAK': '📈 Developing Trend - Trend 2026 active',
            'TREND_STRONG': '📈 Strong Trend - Full Trend 2026 (6-indicator confluence)',
            'UNKNOWN': '❓ Unknown regime'
        }
        return descriptions.get(regime, regime)


# Singleton
_hybrid_strategy = None

def get_hybrid_strategy(config=None):
    global _hybrid_strategy
    if _hybrid_strategy is None:
        _hybrid_strategy = HybridStrategy(config)
    return _hybrid_strategy


if __name__ == "__main__":
    import yfinance as yf

    print("Testing Hybrid Strategy v2.0 (2026)")
    print("=" * 60)

    tickers = ["EURUSD=X", "BTC-USD", "AAPL"]
    strategy = HybridStrategy()

    for ticker in tickers:
        try:
            data = yf.download(ticker, period="1mo", interval="1h", progress=False)
            if hasattr(data.columns, 'levels'):
                data.columns = data.columns.get_level_values(0)
            if len(data) < 30:
                continue

            signal = strategy.get_signal(data)

            print(f"\n{ticker}:")
            print(f"  Regime: {signal.get('regime', 'N/A')} (ADX: {signal.get('regime_adx', 0):.1f})")
            print(f"  Strategy: {signal.get('strategy', 'N/A')}")
            print(f"  Signal: {signal.get('signal', 'N/A')}")
            print(f"  Confidence: {signal.get('confidence', 0):.2f}")
            print(f"  Reason: {signal.get('reason', '')}")
            if signal.get('indicators_used'):
                print(f"  Indicators: {', '.join(signal['indicators_used'])}")
        except Exception as e:
            print(f"\n{ticker}: Error - {e}")

    print("\n" + "=" * 60)
    print("Test complete!")
