"""
Advanced Trading Strategy Module
================================
Obsahuje:
- Fibonacci Retracement/Extension
- Volume Profile Analysis
- VWAP (Volume Weighted Average Price)
- Support/Resistance Detection
- Multi-Timeframe Analysis
- Smart Entry/Exit s konfluencí signálů
"""

import pandas as pd
import numpy as np
from ta.trend import ADXIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import AverageTrueRange, BollingerBands
import yfinance as yf


class AdvancedStrategy:
    """Pokročilá strategie s Fibonacci, Volume a Multi-timeframe analýzou."""

    def __init__(self):
        # Fibonacci levels
        self.fib_levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        self.fib_extensions = [1.272, 1.414, 1.618, 2.0, 2.618]

        # Strategy weights (optimalizováno pro reálné výsledky)
        self.weights = {
            "trend": 0.25,           # Trend je nejdůležitější
            "fibonacci": 0.15,
            "volume": 0.20,          # Volume potvrzuje pohyb
            "momentum": 0.20,        # RSI, MACD
            "support_resistance": 0.10,
            "multi_timeframe": 0.10
        }

        # Minimum confidence pro vstup (sníženo pro víc signálů)
        self.min_confidence = 0.35  # 35%+ = minimum 2 faktory souhlasí

        # Adaptivní učení - ukládá historii úspěšných signálů
        self.signal_history = []
        self.learned_patterns = {}

    def calculate_fibonacci_levels(self, df, lookback=50):
        """Vypočítej Fibonacci retracement úrovně."""
        high = df['High'].tail(lookback).max()
        low = df['Low'].tail(lookback).min()
        diff = high - low

        levels = {}
        for level in self.fib_levels:
            # Pro uptrend: měříme od low
            levels[f"fib_{level}"] = low + (diff * level)

        # Extensions
        for ext in self.fib_extensions:
            levels[f"fib_ext_{ext}"] = high + (diff * (ext - 1))

        return levels, high, low

    def get_fibonacci_signal(self, df, current_price):
        """Analyzuj cenu vůči Fibonacci úrovním."""
        levels, swing_high, swing_low = self.calculate_fibonacci_levels(df)

        signal = {"direction": "NEUTRAL", "strength": 0, "level": None}

        # Najdi nejbližší Fib úroveň
        closest_level = None
        min_distance = float('inf')

        for name, level in levels.items():
            distance = abs(current_price - level) / current_price
            if distance < min_distance:
                min_distance = distance
                closest_level = (name, level)

        # Pokud jsme blízko Fib úrovně (< 0.5%)
        if min_distance < 0.005:
            level_name = closest_level[0]

            # 0.618 a 0.5 jsou silné support/resistance
            if "0.618" in level_name or "0.5" in level_name:
                signal["strength"] = 0.9
            elif "0.382" in level_name or "0.786" in level_name:
                signal["strength"] = 0.7
            else:
                signal["strength"] = 0.5

            signal["level"] = closest_level

            # Určení směru - závisí na trendu a pozici
            if current_price > swing_low + (swing_high - swing_low) * 0.5:
                # V horní polovině - hledáme SHORT při resistanci
                if current_price >= closest_level[1]:
                    signal["direction"] = "SELL"
                else:
                    signal["direction"] = "BUY"
            else:
                # V dolní polovině - hledáme LONG při supportu
                if current_price <= closest_level[1]:
                    signal["direction"] = "BUY"
                else:
                    signal["direction"] = "SELL"

        return signal

    def calculate_vwap(self, df):
        """Vypočítej VWAP (Volume Weighted Average Price)."""
        df = df.copy()
        df['typical_price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['vwap'] = (df['typical_price'] * df['Volume']).cumsum() / df['Volume'].cumsum()
        return df['vwap']

    def calculate_volume_profile(self, df, bins=20):
        """Vypočítej Volume Profile - kde se obchodovalo nejvíc."""
        price_range = df['Close'].max() - df['Close'].min()
        bin_size = price_range / bins

        volume_at_price = {}
        for idx, row in df.iterrows():
            price_bin = int((row['Close'] - df['Close'].min()) / bin_size)
            if price_bin not in volume_at_price:
                volume_at_price[price_bin] = 0
            volume_at_price[price_bin] += row['Volume']

        # Najdi POC (Point of Control) - nejvyšší volume
        poc_bin = max(volume_at_price, key=volume_at_price.get)
        poc_price = df['Close'].min() + (poc_bin + 0.5) * bin_size

        # Value Area (70% volume)
        total_volume = sum(volume_at_price.values())
        sorted_bins = sorted(volume_at_price.items(), key=lambda x: x[1], reverse=True)

        va_volume = 0
        va_bins = []
        for bin_idx, vol in sorted_bins:
            va_volume += vol
            va_bins.append(bin_idx)
            if va_volume >= total_volume * 0.7:
                break

        va_high = df['Close'].min() + (max(va_bins) + 1) * bin_size
        va_low = df['Close'].min() + min(va_bins) * bin_size

        return {
            "poc": poc_price,
            "va_high": va_high,
            "va_low": va_low,
            "volume_at_price": volume_at_price
        }

    def get_volume_signal(self, df, current_price):
        """Analyzuj volume pro signál."""
        signal = {"direction": "NEUTRAL", "strength": 0}

        # VWAP
        vwap = self.calculate_vwap(df)
        current_vwap = vwap.iloc[-1]

        # Volume Profile
        vp = self.calculate_volume_profile(df)

        # Volume trend (posledních 5 svíček vs průměr)
        recent_vol = df['Volume'].tail(5).mean()
        avg_vol = df['Volume'].mean()
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1

        # Signál založený na VWAP a Volume
        if current_price > current_vwap and vol_ratio > 1.2:
            # Cena nad VWAP s vysokým volume = bullish
            signal["direction"] = "BUY"
            signal["strength"] = min(0.9, 0.5 + (vol_ratio - 1) * 0.4)
        elif current_price < current_vwap and vol_ratio > 1.2:
            # Cena pod VWAP s vysokým volume = bearish
            signal["direction"] = "SELL"
            signal["strength"] = min(0.9, 0.5 + (vol_ratio - 1) * 0.4)
        elif vol_ratio < 0.5:
            # Nízký volume = nejistota
            signal["strength"] = 0.2

        # Přidej info o Value Area
        if vp["va_low"] <= current_price <= vp["va_high"]:
            signal["in_value_area"] = True
        else:
            signal["in_value_area"] = False
            # Mimo Value Area = potenciální breakout
            signal["strength"] *= 1.2

        return signal

    def detect_support_resistance(self, df, lookback=100, tolerance=0.02):
        """Detekuj support a resistance úrovně z historických dat."""
        highs = df['High'].tail(lookback)
        lows = df['Low'].tail(lookback)

        levels = []

        # Najdi lokální maxima a minima
        for i in range(2, len(highs) - 2):
            # Lokální maximum (resistance)
            if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and \
               highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]:
                levels.append({"price": highs.iloc[i], "type": "resistance", "touches": 1})

            # Lokální minimum (support)
            if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i-2] and \
               lows.iloc[i] < lows.iloc[i+1] and lows.iloc[i] < lows.iloc[i+2]:
                levels.append({"price": lows.iloc[i], "type": "support", "touches": 1})

        # Konsoliduj podobné úrovně
        consolidated = []
        for level in levels:
            merged = False
            for c_level in consolidated:
                if abs(level["price"] - c_level["price"]) / c_level["price"] < tolerance:
                    c_level["touches"] += 1
                    c_level["price"] = (c_level["price"] + level["price"]) / 2
                    merged = True
                    break
            if not merged:
                consolidated.append(level)

        # Seřaď podle počtu dotyků (silnější úrovně)
        consolidated.sort(key=lambda x: x["touches"], reverse=True)

        return consolidated[:10]  # Top 10 úrovní

    def get_sr_signal(self, df, current_price):
        """Signál založený na support/resistance."""
        signal = {"direction": "NEUTRAL", "strength": 0, "level": None}

        levels = self.detect_support_resistance(df)

        # Najdi nejbližší úroveň
        closest = None
        min_dist = float('inf')

        for level in levels:
            dist = abs(current_price - level["price"]) / current_price
            if dist < min_dist:
                min_dist = dist
                closest = level

        if closest and min_dist < 0.01:  # Blízko úrovně (< 1%)
            signal["level"] = closest
            # Síla závisí na počtu dotyků
            signal["strength"] = min(0.9, 0.4 + closest["touches"] * 0.15)

            if closest["type"] == "support":
                signal["direction"] = "BUY"  # Bounce od supportu
            else:
                signal["direction"] = "SELL"  # Rejection od resistance

        return signal

    def get_multi_timeframe_signal(self, ticker, current_tf_signal):
        """Ověř signál na vyšším timeframe."""
        try:
            # Získej data z vyššího TF (1h pro 5m trades)
            df_1h = yf.download(ticker, period="1mo", interval="1h", progress=False)

            if df_1h.empty or len(df_1h) < 20:
                return {"confirms": True, "strength": 0.5}

            # Flatten columns if multi-level
            if isinstance(df_1h.columns, pd.MultiIndex):
                df_1h.columns = df_1h.columns.get_level_values(0)

            # Základní trend na 1h
            ema_20 = EMAIndicator(df_1h['Close'], window=20).ema_indicator()
            ema_50 = EMAIndicator(df_1h['Close'], window=50).ema_indicator()

            current_close = df_1h['Close'].iloc[-1]

            htf_trend = "NEUTRAL"
            if current_close > ema_20.iloc[-1] > ema_50.iloc[-1]:
                htf_trend = "BUY"
            elif current_close < ema_20.iloc[-1] < ema_50.iloc[-1]:
                htf_trend = "SELL"

            # Ověř shodu
            if htf_trend == current_tf_signal:
                return {"confirms": True, "strength": 0.9, "htf_trend": htf_trend}
            elif htf_trend == "NEUTRAL":
                return {"confirms": True, "strength": 0.6, "htf_trend": htf_trend}
            else:
                return {"confirms": False, "strength": 0.3, "htf_trend": htf_trend}

        except Exception as e:
            return {"confirms": True, "strength": 0.5, "error": str(e)}

    def calculate_trend_strength(self, df):
        """Vypočítej sílu trendu pomocí ADX a EMA."""
        adx = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
        adx_value = adx.adx().iloc[-1]

        di_plus = adx.adx_pos().iloc[-1]
        di_minus = adx.adx_neg().iloc[-1]

        ema_20 = EMAIndicator(df['Close'], window=20).ema_indicator().iloc[-1]
        ema_50 = EMAIndicator(df['Close'], window=50).ema_indicator().iloc[-1]
        current_price = df['Close'].iloc[-1]

        signal = {"direction": "NEUTRAL", "strength": 0}

        # Trend direction
        if di_plus > di_minus and current_price > ema_20 > ema_50:
            signal["direction"] = "BUY"
            signal["strength"] = min(0.9, adx_value / 50)
        elif di_minus > di_plus and current_price < ema_20 < ema_50:
            signal["direction"] = "SELL"
            signal["strength"] = min(0.9, adx_value / 50)

        return signal

    def calculate_momentum(self, df):
        """Vypočítej momentum signály (RSI, Stochastic, MACD)."""
        rsi = RSIIndicator(df['Close'], window=14).rsi().iloc[-1]

        stoch = StochasticOscillator(df['High'], df['Low'], df['Close'], window=14)
        stoch_k = stoch.stoch().iloc[-1]
        stoch_d = stoch.stoch_signal().iloc[-1]

        macd = MACD(df['Close'])
        macd_line = macd.macd().iloc[-1]
        macd_signal = macd.macd_signal().iloc[-1]
        macd_hist = macd.macd_diff().iloc[-1]

        signal = {"direction": "NEUTRAL", "strength": 0}

        bullish_count = 0
        bearish_count = 0

        # RSI
        if rsi < 30:
            bullish_count += 1
        elif rsi > 70:
            bearish_count += 1

        # Stochastic
        if stoch_k < 20 and stoch_k > stoch_d:
            bullish_count += 1
        elif stoch_k > 80 and stoch_k < stoch_d:
            bearish_count += 1

        # MACD
        if macd_hist > 0 and macd_line > macd_signal:
            bullish_count += 1
        elif macd_hist < 0 and macd_line < macd_signal:
            bearish_count += 1

        if bullish_count >= 2:
            signal["direction"] = "BUY"
            signal["strength"] = bullish_count / 3
        elif bearish_count >= 2:
            signal["direction"] = "SELL"
            signal["strength"] = bearish_count / 3

        return signal

    def get_signal(self, df, ticker=None, config=None):
        """
        Hlavní metoda - kombinuje všechny strategie pro finální signál.

        Returns:
            dict: {
                "signal": "BUY" | "SELL" | "NEUTRAL",
                "confidence": 0.0-1.0,
                "reasons": [...],
                "sl": stop_loss_price,
                "tp": take_profit_price
            }
        """
        if len(df) < 50:
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Nedostatek dat"}

        current_price = df['Close'].iloc[-1]

        # Sbírej signály ze všech strategií
        signals = {}
        reasons = []

        # 1. Trend
        trend = self.calculate_trend_strength(df)
        signals["trend"] = trend
        if trend["strength"] > 0.5:
            reasons.append(f"Trend: {trend['direction']} ({trend['strength']:.0%})")

        # 2. Fibonacci
        fib = self.get_fibonacci_signal(df, current_price)
        signals["fibonacci"] = fib
        if fib["strength"] > 0.5:
            level_name = fib["level"][0] if fib["level"] else "N/A"
            reasons.append(f"Fib {level_name}: {fib['direction']}")

        # 3. Volume
        vol = self.get_volume_signal(df, current_price)
        signals["volume"] = vol
        if vol["strength"] > 0.5:
            reasons.append(f"Volume: {vol['direction']} ({vol['strength']:.0%})")

        # 4. Momentum
        mom = self.calculate_momentum(df)
        signals["momentum"] = mom
        if mom["strength"] > 0.5:
            reasons.append(f"Momentum: {mom['direction']}")

        # 5. Support/Resistance
        sr = self.get_sr_signal(df, current_price)
        signals["support_resistance"] = sr
        if sr["strength"] > 0.5:
            reasons.append(f"S/R: {sr['direction']} @ {sr['level']['price']:.4f}")

        # 6. Multi-timeframe (pokud máme ticker)
        mtf = {"confirms": True, "strength": 0.5}
        if ticker:
            # Určíme preliminary direction pro MTF check
            buy_score = sum(1 for s in signals.values() if s.get("direction") == "BUY")
            sell_score = sum(1 for s in signals.values() if s.get("direction") == "SELL")
            prelim_direction = "BUY" if buy_score > sell_score else "SELL" if sell_score > buy_score else "NEUTRAL"

            mtf = self.get_multi_timeframe_signal(ticker, prelim_direction)
            signals["multi_timeframe"] = mtf
            if mtf.get("confirms"):
                reasons.append(f"MTF confirms: {mtf.get('htf_trend', 'N/A')}")
            else:
                reasons.append(f"MTF disagrees: {mtf.get('htf_trend', 'N/A')}")

        # Vypočítej celkový confidence score
        buy_confidence = 0
        sell_confidence = 0

        for strategy_name, strategy_signal in signals.items():
            weight = self.weights.get(strategy_name, 0.1)
            strength = strategy_signal.get("strength", 0)
            direction = strategy_signal.get("direction", "NEUTRAL")

            if direction == "BUY":
                buy_confidence += weight * strength
            elif direction == "SELL":
                sell_confidence += weight * strength

        # MTF modifier
        if not mtf.get("confirms", True):
            buy_confidence *= 0.5
            sell_confidence *= 0.5

        # Finální rozhodnutí
        final_signal = "NEUTRAL"
        confidence = 0

        if buy_confidence > sell_confidence and buy_confidence >= self.min_confidence:
            final_signal = "BUY"
            confidence = buy_confidence
        elif sell_confidence > buy_confidence and sell_confidence >= self.min_confidence:
            final_signal = "SELL"
            confidence = sell_confidence
        else:
            confidence = max(buy_confidence, sell_confidence)

        # Výpočet SL/TP
        atr = AverageTrueRange(df['High'], df['Low'], df['Close'], window=14)
        atr_value = atr.average_true_range().iloc[-1]

        if final_signal == "BUY":
            sl = current_price - (atr_value * 1.5)
            tp = current_price + (atr_value * 2.0)  # R:R 1.33
        elif final_signal == "SELL":
            sl = current_price + (atr_value * 1.5)
            tp = current_price - (atr_value * 2.0)
        else:
            sl = tp = None

        return {
            "signal": final_signal,
            "confidence": confidence,
            "reasons": reasons,
            "sl": sl,
            "tp": tp,
            "buy_score": buy_confidence,
            "sell_score": sell_confidence,
            "signals": signals
        }


def test_advanced_strategy():
    """Test pokročilé strategie."""
    print("=" * 70)
    print("TEST ADVANCED STRATEGY")
    print("=" * 70)

    strategy = AdvancedStrategy()

    # Test na ETH
    ticker = "ETH-USD"
    df = yf.download(ticker, period="3mo", interval="5m", progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if not df.empty:
        result = strategy.get_signal(df, ticker=ticker)

        print(f"\n📊 {ticker} Analysis:")
        print(f"   Signal: {result['signal']}")
        print(f"   Confidence: {result['confidence']:.1%}")
        print(f"   Buy Score: {result['buy_score']:.2f}")
        print(f"   Sell Score: {result['sell_score']:.2f}")
        print(f"\n   Reasons:")
        for reason in result['reasons']:
            print(f"   - {reason}")

        if result['sl'] and result['tp']:
            print(f"\n   SL: ${result['sl']:.2f}")
            print(f"   TP: ${result['tp']:.2f}")


if __name__ == "__main__":
    test_advanced_strategy()
