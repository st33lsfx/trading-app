"""
Mean Reversion Strategy v2.0
============================
Vylepšení:
- Trend filter (EMA 50) - neobchoduj proti trendu
- Volatility filter - vyhni se příliš klidným/divokým trhům
- Volume confirmation - vyšší confidence při vysokém volume
- Session filter - obchoduj jen v aktivních hodinách
- Minimum profit check - neotvírej trade s malým potenciálem
- Lepší SL/TP management

Backtest výsledky (původní):
- Win Rate: 56.1%
- Return bez páky: 33.5%
"""

import pandas as pd
import numpy as np
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.trend import EMAIndicator


class MeanReversionStrategy:
    """Mean Reversion strategie s pokročilými filtry."""

    def __init__(self, config=None):
        self.config = config or {}

        # === BOLLINGER BANDS ===
        self.bb_window = self.config.get("bb_window", 20)
        self.bb_std = self.config.get("bb_std", 2)

        # === RSI ===
        self.rsi_period = self.config.get("rsi_period", 14)
        self.rsi_oversold = self.config.get("rsi_oversold", 38)  # Mírnější pro více signálů
        self.rsi_overbought = self.config.get("rsi_overbought", 62)

        # === RISK MANAGEMENT ===
        self.atr_sl_mult = self.config.get("atr_sl_mult", 2.0)  # Wider SL = méně SL hitů
        self.min_rr_ratio = self.config.get("min_rr_ratio", 1.2)  # Nižší R:R = více WR

        # === FILTERS ===
        # Trend filter VYPNUT - mean reversion obchoduje proti krátkodobému trendu
        self.use_trend_filter = self.config.get("use_trend_filter", False)
        self.use_volatility_filter = self.config.get("use_volatility_filter", True)
        self.use_volume_filter = self.config.get("use_volume_filter", False)  # Volume data není vždy spolehlivá
        self.use_session_filter = self.config.get("use_session_filter", False)

        # Volatility bounds (BB width as % of price)
        self.min_volatility = self.config.get("min_volatility", 0.003)  # 0.3% min
        self.max_volatility = self.config.get("max_volatility", 0.10)   # 10% max

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

        # EMA pro trend
        df['ema_50'] = EMAIndicator(df['Close'], window=50).ema_indicator()
        df['ema_20'] = EMAIndicator(df['Close'], window=20).ema_indicator()
        
        # ADX pro detekci trendu (< 25 = ranging, > 25 = trending)
        adx_indicator = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
        df['adx'] = adx_indicator.adx()

        # Volume MA (pokud máme volume data)
        if 'Volume' in df.columns and df['Volume'].sum() > 0:
            df['volume_ma'] = df['Volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['Volume'] / df['volume_ma']
        else:
            df['volume_ratio'] = 1.0

        # % distance from bands
        df['dist_from_lower'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # Trend direction (price vs EMA50)
        df['trend'] = np.where(df['Close'] > df['ema_50'], 'UP', 'DOWN')

        return df

    def is_good_session(self):
        """
        Check if current time is good for trading.
        Best hours: London (8-17 UTC), NY (13-22 UTC), Overlap (13-17 UTC)
        """
        if not self.use_session_filter:
            return True, "Session filter disabled"

        now = datetime.utcnow()
        hour = now.hour
        weekday = now.weekday()  # 0=Monday, 6=Sunday

        # Weekend - Forex closed (but crypto open)
        if weekday >= 5:
            return True, "Weekend (crypto only)"  # Allow crypto

        # Best trading hours (UTC)
        # London: 8-17, NY: 13-22, Overlap: 13-17
        if 8 <= hour <= 22:
            if 13 <= hour <= 17:
                return True, "London/NY overlap - HIGH LIQUIDITY"
            elif 8 <= hour <= 12:
                return True, "London session"
            else:
                return True, "NY session"

        # Asian session (less liquid for Forex)
        if 0 <= hour <= 7:
            return True, "Asian session (lower liquidity)"

        return True, "Active trading hours"

    def check_filters(self, df, signal_direction):
        """
        Check all filters and return (passed, reasons).
        """
        reasons = []
        passed = True
        row = df.iloc[-1]

        # 1. TREND FILTER
        if self.use_trend_filter:
            trend = row.get('trend', 'NEUTRAL')
            
            # Mean reversion: Trade WITH the trend for higher probability
            # BUY only in uptrend, SELL only in downtrend
            if signal_direction == "BUY" and trend == "DOWN":
                # Allow counter-trend if RSI is extremely oversold
                if row['rsi'] > 25:  # Not extreme enough
                    passed = False
                    reasons.append(f"❌ Trend filter: DOWN trend, risky BUY")
                else:
                    reasons.append(f"⚠️ Counter-trend BUY (extreme RSI)")
            elif signal_direction == "SELL" and trend == "UP":
                if row['rsi'] < 75:  # Not extreme enough
                    passed = False
                    reasons.append(f"❌ Trend filter: UP trend, risky SELL")
                else:
                    reasons.append(f"⚠️ Counter-trend SELL (extreme RSI)")
            else:
                reasons.append(f"✅ Trend aligned ({trend})")

        # 1.5 ADX FILTER (CRITICAL for mean reversion!)
        # ADX < 25 = ranging market (GOOD for mean reversion)
        # ADX > 25 = trending market (BAD - skip trade)
        adx = row.get('adx', 0)
        if adx > 30:
            passed = False
            reasons.append(f"❌ Strong trend (ADX {adx:.1f}) - mean reversion risky")
        elif adx > 25:
            # Warning but still allow with lower confidence
            reasons.append(f"⚠️ Trend forming (ADX {adx:.1f})")
        else:
            reasons.append(f"✅ Ranging market (ADX {adx:.1f})")

        # 2. VOLATILITY FILTER
        if self.use_volatility_filter:
            bb_width = row.get('bb_width', 0)

            if bb_width < self.min_volatility:
                passed = False
                reasons.append(f"❌ Low volatility ({bb_width:.2%}) - no movement")
            elif bb_width > self.max_volatility:
                passed = False
                reasons.append(f"❌ High volatility ({bb_width:.2%}) - too risky")
            else:
                reasons.append(f"✅ Volatility OK ({bb_width:.2%})")

        # 3. VOLUME FILTER
        if self.use_volume_filter:
            volume_ratio = row.get('volume_ratio', 1.0)

            if volume_ratio < 0.5:
                passed = False
                reasons.append(f"❌ Low volume ({volume_ratio:.1f}x avg)")
            elif volume_ratio > 0.8:
                reasons.append(f"✅ Good volume ({volume_ratio:.1f}x avg)")
            else:
                reasons.append(f"⚠️ Below avg volume ({volume_ratio:.1f}x)")

        # 4. SESSION FILTER
        session_ok, session_msg = self.is_good_session()
        if not session_ok:
            passed = False
        reasons.append(f"📅 {session_msg}")

        return passed, reasons

    def get_signal(self, df, config=None):
        """
        Získej trading signál s pokročilými filtry.

        Returns:
            dict s klíči: signal, confidence, sl, tp, rsi, reason, filters
        """
        if len(df) < 60:  # Potřebujeme víc dat pro EMA50
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Nedostatek dat", "rsi": 50}

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
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Missing indicators", "rsi": 50}

        signal = "NEUTRAL"
        confidence = 0
        reason = ""
        sl = None
        tp = None
        filter_results = []

        # =============================================
        # SIGNAL DETECTION
        # =============================================

        potential_signal = None
        base_confidence = 0.6

        # Tolerance pro BB dotek (0.3% = cena může být mírně nad/pod BB)
        bb_tolerance = 0.003  # 0.3%
        bb_lower_with_tolerance = bb_lower * (1 + bb_tolerance)
        bb_upper_with_tolerance = bb_upper * (1 - bb_tolerance)
        
        # === R:R GUARANTEED CALCULATION ===
        # SL = ATR × 2.0, TP = ATR × 4.0 → R:R = 1:2
        sl_distance = atr * self.atr_sl_mult  # Default 2.0
        tp_distance = atr * 4.0  # Guarantee 1:2 R:R

        # BUY SIGNAL: Cena blízko spodní BB + RSI oversold
        if row['Low'] <= bb_lower_with_tolerance and rsi < self.rsi_oversold:
            potential_signal = "BUY"
            base_confidence = 0.6 + (self.rsi_oversold - rsi) / 100
            sl = current_price - sl_distance
            tp = current_price + tp_distance  # ATR-based, NOT bb_mid!

        # SELL SIGNAL: Cena blízko horní BB + RSI overbought
        elif row['High'] >= bb_upper_with_tolerance and rsi > self.rsi_overbought:
            potential_signal = "SELL"
            base_confidence = 0.6 + (rsi - self.rsi_overbought) / 100
            sl = current_price + sl_distance
            tp = current_price - tp_distance  # ATR-based, NOT bb_mid!
        
        # =============================================
        # FALLBACK: RSI-only signal without BB requirement
        # =============================================
        elif rsi < 35:  # Oversold zone
            potential_signal = "BUY"
            base_confidence = 0.55 + (35 - rsi) / 100
            sl = current_price - (sl_distance * 1.2)  # Slightly wider
            tp = current_price + tp_distance
        
        elif rsi > 65:  # Overbought zone
            potential_signal = "SELL"
            base_confidence = 0.55 + (rsi - 65) / 100
            sl = current_price + (sl_distance * 1.2)  # Slightly wider
            tp = current_price - tp_distance  # ATR×4 for 1:2 R:R

        # =============================================
        # APPLY FILTERS
        # =============================================

        if potential_signal:
            filters_passed, filter_results = self.check_filters(df, potential_signal)

            # Calculate Risk:Reward
            if potential_signal == "BUY":
                risk = current_price - sl
                reward = tp - current_price
            else:
                risk = sl - current_price
                reward = current_price - tp

            rr_ratio = reward / risk if risk > 0 else 0

            # Minimum R:R check
            if rr_ratio < self.min_rr_ratio:
                filters_passed = False
                filter_results.append(f"❌ R:R too low ({rr_ratio:.2f}, need {self.min_rr_ratio})")
            else:
                filter_results.append(f"✅ R:R = {rr_ratio:.2f}")

            if filters_passed:
                signal = potential_signal
                confidence = min(0.9, base_confidence)

                # Boost confidence if volume is high
                volume_ratio = row.get('volume_ratio', 1.0)
                if volume_ratio > 1.5:
                    confidence = min(0.95, confidence + 0.1)

                reason = f"Mean reversion {signal}: RSI={rsi:.1f}, BB touch"
            else:
                reason = f"Signal {potential_signal} blocked by filters"

        # No signal
        else:
            dist = row['dist_from_lower']
            if 0.3 < dist < 0.7:
                reason = f"Price in middle zone ({dist:.0%}), waiting"
            elif dist <= 0.3:
                reason = f"Near lower BB, RSI={rsi:.1f} (need <{self.rsi_oversold})"
            else:
                reason = f"Near upper BB, RSI={rsi:.1f} (need >{self.rsi_overbought})"

        return {
            "signal": signal,
            "confidence": confidence,
            "sl": sl,
            "tp": tp,
            "rsi": rsi,
            "reason": reason,
            "bb_mid": bb_mid,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "filters": filter_results,
            "trend": row.get('trend', 'NEUTRAL'),
            "volatility": row.get('bb_width', 0)
        }


# Singleton instance
_strategy_instance = None


def get_strategy(config=None):
    """Získej singleton instanci strategie."""
    global _strategy_instance
    if _strategy_instance is None or config:
        _strategy_instance = MeanReversionStrategy(config)
    return _strategy_instance


def test_strategy():
    """Test strategie."""
    import yfinance as yf

    print("=" * 60)
    print("TEST MEAN REVERSION STRATEGY v2.0")
    print("=" * 60)

    strategy = MeanReversionStrategy()

    tickers = ["ETH-USD", "GBPUSD=X", "AMD", "NZDUSD=X"]

    for ticker in tickers:
        print(f"\n{'='*40}")
        print(f"Testing: {ticker}")
        print(f"{'='*40}")

        df = yf.download(ticker, period="1mo", interval="1h", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if not df.empty:
            result = strategy.get_signal(df)
            print(f"Signal: {result['signal']}")
            print(f"Confidence: {result['confidence']:.1%}")
            print(f"RSI: {result['rsi']:.1f}")
            print(f"Trend: {result.get('trend', 'N/A')}")
            print(f"Volatility: {result.get('volatility', 0):.2%}")
            print(f"Reason: {result['reason']}")

            if result.get('filters'):
                print("\nFilters:")
                for f in result['filters']:
                    print(f"  {f}")

            if result['sl']:
                print(f"\nSL: ${result['sl']:.4f}")
                print(f"TP: ${result['tp']:.4f}")


if __name__ == "__main__":
    test_strategy()
