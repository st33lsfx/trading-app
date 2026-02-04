"""
Mean Reversion Strategy
=======================
Backtest výsledky (2 měsíce, 8 assetů):
- Win Rate: 56.1%
- Return bez páky: 33.5%
- S pákou 1:10: 2000 Kč → 8693 Kč
- 10 obchodů denně

Strategie:
- BUY když cena dotkne spodní Bollinger Band + RSI < 40
- SELL když cena dotkne horní Bollinger Band + RSI > 60
- TP na střední BB (mean reversion)
- SL na 2x ATR
"""

import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange


class MeanReversionStrategy:
    """Mean Reversion strategie s Bollinger Bands."""

    def __init__(self, config=None):
        self.config = config or {}

        # Parametry (optimalizované z backtestu)
        self.bb_window = self.config.get("bb_window", 20)
        self.bb_std = self.config.get("bb_std", 2)
        self.rsi_period = self.config.get("rsi_period", 14)
        self.rsi_oversold = self.config.get("rsi_oversold", 40)
        self.rsi_overbought = self.config.get("rsi_overbought", 60)
        self.atr_sl_mult = self.config.get("atr_sl_mult", 2.0)

    def add_indicators(self, df):
        """Přidej všechny potřebné indikátory."""
        df = df.copy()

        # Bollinger Bands
        bb = BollingerBands(df['Close'], window=self.bb_window, window_dev=self.bb_std)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_mid'] = bb.bollinger_mavg()
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']

        # RSI
        df['rsi'] = RSIIndicator(df['Close'], window=self.rsi_period).rsi()

        # ATR pro SL
        df['atr'] = AverageTrueRange(df['High'], df['Low'], df['Close'], window=14).average_true_range()

        # % distance from bands
        df['dist_from_lower'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        return df

    def get_signal(self, df, config=None):
        """
        Získej trading signál.

        Returns:
            dict s klíči: signal, confidence, sl, tp, rsi, reason
        """
        if len(df) < 30:
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Nedostatek dat"}

        # Přidej indikátory
        df = self.add_indicators(df)

        row = df.iloc[-1]
        prev = df.iloc[-2]

        current_price = row['Close']
        bb_lower = row['bb_lower']
        bb_upper = row['bb_upper']
        bb_mid = row['bb_mid']
        rsi = row['rsi']
        atr = row['atr']

        if pd.isna(bb_lower) or pd.isna(rsi) or pd.isna(atr):
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Missing indicators"}

        signal = "NEUTRAL"
        confidence = 0
        reason = ""
        sl = None
        tp = None

        # BUY SIGNAL: Cena u spodní BB + RSI nízké
        if row['Low'] <= bb_lower and rsi < self.rsi_oversold:
            signal = "BUY"
            confidence = 0.7 + (self.rsi_oversold - rsi) / 100  # Vyšší confidence při nižším RSI
            confidence = min(0.9, confidence)
            reason = f"Mean reversion BUY: RSI={rsi:.1f}, Price at lower BB"

            sl = current_price - (atr * self.atr_sl_mult)
            tp = bb_mid  # TP na střední BB

        # SELL SIGNAL: Cena u horní BB + RSI vysoké
        elif row['High'] >= bb_upper and rsi > self.rsi_overbought:
            signal = "SELL"
            confidence = 0.7 + (rsi - self.rsi_overbought) / 100
            confidence = min(0.9, confidence)
            reason = f"Mean reversion SELL: RSI={rsi:.1f}, Price at upper BB"

            sl = current_price + (atr * self.atr_sl_mult)
            tp = bb_mid

        # Žádný signál - cena je ve středu
        else:
            dist = row['dist_from_lower']
            if 0.3 < dist < 0.7:
                reason = f"Price in middle zone ({dist:.0%})"
            elif dist <= 0.3:
                reason = f"Near lower BB but RSI={rsi:.1f} not oversold"
            else:
                reason = f"Near upper BB but RSI={rsi:.1f} not overbought"

        return {
            "signal": signal,
            "confidence": confidence,
            "sl": sl,
            "tp": tp,
            "rsi": rsi,
            "reason": reason,
            "bb_mid": bb_mid,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower
        }


# Singleton instance pro použití v botu
_strategy_instance = None


def get_strategy():
    """Získej singleton instanci strategie."""
    global _strategy_instance
    if _strategy_instance is None:
        _strategy_instance = MeanReversionStrategy()
    return _strategy_instance


def test_strategy():
    """Test strategie."""
    import yfinance as yf

    print("=" * 60)
    print("TEST MEAN REVERSION STRATEGY")
    print("=" * 60)

    strategy = MeanReversionStrategy()

    tickers = ["ETH-USD", "GBPUSD=X", "AMD"]

    for ticker in tickers:
        df = yf.download(ticker, period="1mo", interval="1h", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if not df.empty:
            result = strategy.get_signal(df)
            print(f"\n{ticker}:")
            print(f"  Signal: {result['signal']}")
            print(f"  Confidence: {result['confidence']:.1%}")
            print(f"  RSI: {result['rsi']:.1f}")
            print(f"  Reason: {result['reason']}")

            if result['sl']:
                print(f"  SL: ${result['sl']:.4f}")
                print(f"  TP: ${result['tp']:.4f}")


if __name__ == "__main__":
    test_strategy()
