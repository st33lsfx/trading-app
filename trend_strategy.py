"""
Trend Following Strategy v2.0 (2026 Guide)
===========================================
The Ultimate Trend System combining the TOP indicators
from the QuantVPS 2026 Guide for maximum profitability.

PRIMARY (Entry Core):
1. Supertrend (ATR period=10, mult=3.0) - Trend direction + dynamic trailing stop
2. ADX (14) - Trend strength confirmation (>25 required)
3. Hull Moving Average (9/21) - Low-lag crossovers for precise timing

CONFIRMATION:
4. VWAP - Institutional value bias (above=bullish, below=bearish)
5. MACD (12,26,9) - Momentum confirmation via histogram
6. Ichimoku Cloud - Support/resistance zones

ENTRY RULES:
- ADX > 25 required (baseline)
- Minimum 3 of 6 indicators aligned (confluence)
- Multi-timeframe alignment with 4H direction
- Confirmation candle required

RISK MANAGEMENT:
- SL: Supertrend level (dynamic ATR-based trailing stop)
- TP: 2.0x risk distance minimum (R:R >= 1:2.0)
- Trailing stop follows Supertrend line
"""

import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, MACD
from ta.volatility import AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice


class TrendStrategy:
    """Ultimate Trend Following Strategy 2026 - 6-Indicator Confluence System."""

    def __init__(self, config=None):
        self.config = config or {}

        # === SUPERTREND (ATR-based trend + trailing stop) ===
        self.st_period = self.config.get('st_period', 10)
        self.st_multiplier = self.config.get('st_multiplier', 3.0)

        # === HMA (Hull Moving Average - low lag) ===
        self.hma_fast = self.config.get('hma_fast', 9)
        self.hma_slow = self.config.get('hma_slow', 21)

        # === ADX (trend strength gate) ===
        self.adx_min = self.config.get('adx_min', 25)

        # === MACD (momentum) ===
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal_period = 9

        # === ICHIMOKU (cloud support/resistance) ===
        self.ichi_tenkan = 9
        self.ichi_kijun = 26
        self.ichi_senkou_b = 52

        # === RSI (supplementary) ===
        self.rsi_period = 14

        # === RISK MANAGEMENT ===
        self.min_rr_ratio = self.config.get('min_rr_ratio', 2.0)
        self.min_confluence = self.config.get('min_confluence', 3)
        self.atr_sl_mult = self.config.get('atr_sl_mult', 2.0)

        # Internal state
        self._has_real_vwap = False

    # =========================================================
    # INDICATOR CALCULATIONS
    # =========================================================

    def _calculate_wma(self, series, window):
        """Weighted Moving Average."""
        weights = np.arange(1, window + 1)
        return series.rolling(window).apply(
            lambda x: np.dot(x, weights) / weights.sum(), raw=True
        )

    def _calculate_hma(self, series, window):
        """Hull Moving Average - eliminates lag while maintaining smoothness."""
        half_len = max(1, int(window / 2))
        sqrt_len = max(1, int(np.sqrt(window)))
        wma_half = self._calculate_wma(series, half_len)
        wma_full = self._calculate_wma(series, window)
        raw_hma = 2 * wma_half - wma_full
        return self._calculate_wma(raw_hma, sqrt_len)

    def _calculate_supertrend(self, df):
        """
        Calculate Supertrend indicator.
        Returns (supertrend_line, direction) where direction: 1=bullish, -1=bearish.
        The supertrend line serves as a dynamic trailing stop.
        """
        hl2 = (df['High'] + df['Low']) / 2
        atr = AverageTrueRange(
            df['High'], df['Low'], df['Close'], window=self.st_period
        ).average_true_range()

        upper_basic = hl2 + (self.st_multiplier * atr)
        lower_basic = hl2 - (self.st_multiplier * atr)

        n = len(df)
        upper_band = np.zeros(n)
        lower_band = np.zeros(n)
        supertrend = np.zeros(n)
        direction = np.ones(n, dtype=int)

        close = df['Close'].values
        ub_vals = upper_basic.values
        lb_vals = lower_basic.values

        # Initialize first bar
        upper_band[0] = ub_vals[0] if not np.isnan(ub_vals[0]) else close[0] * 1.03
        lower_band[0] = lb_vals[0] if not np.isnan(lb_vals[0]) else close[0] * 0.97
        supertrend[0] = lower_band[0]

        for i in range(1, n):
            ub = ub_vals[i]
            lb = lb_vals[i]

            if np.isnan(ub) or np.isnan(lb):
                upper_band[i] = upper_band[i - 1]
                lower_band[i] = lower_band[i - 1]
                supertrend[i] = supertrend[i - 1]
                direction[i] = direction[i - 1]
                continue

            # Ratchet lower band UP (never decrease in uptrend)
            if lb > lower_band[i - 1] or close[i - 1] < lower_band[i - 1]:
                lower_band[i] = lb
            else:
                lower_band[i] = lower_band[i - 1]

            # Ratchet upper band DOWN (never increase in downtrend)
            if ub < upper_band[i - 1] or close[i - 1] > upper_band[i - 1]:
                upper_band[i] = ub
            else:
                upper_band[i] = upper_band[i - 1]

            # Determine direction based on previous state
            if supertrend[i - 1] == upper_band[i - 1]:
                # Was bearish (using upper band as resistance)
                if close[i] > upper_band[i]:
                    supertrend[i] = lower_band[i]
                    direction[i] = 1  # Flip to bullish
                else:
                    supertrend[i] = upper_band[i]
                    direction[i] = -1  # Stay bearish
            else:
                # Was bullish (using lower band as support)
                if close[i] < lower_band[i]:
                    supertrend[i] = upper_band[i]
                    direction[i] = -1  # Flip to bearish
                else:
                    supertrend[i] = lower_band[i]
                    direction[i] = 1  # Stay bullish

        return (
            pd.Series(supertrend, index=df.index),
            pd.Series(direction, index=df.index)
        )

    def _calculate_ichimoku(self, df):
        """
        Calculate Ichimoku Cloud components manually.
        Returns span_a and span_b shifted to align with current price position.
        """
        high = df['High']
        low = df['Low']

        # Tenkan-sen (Conversion Line) - 9 period
        high_9 = high.rolling(self.ichi_tenkan).max()
        low_9 = low.rolling(self.ichi_tenkan).min()
        tenkan = (high_9 + low_9) / 2

        # Kijun-sen (Base Line) - 26 period
        high_26 = high.rolling(self.ichi_kijun).max()
        low_26 = low.rolling(self.ichi_kijun).min()
        kijun = (high_26 + low_26) / 2

        # Senkou Span A - (Tenkan + Kijun) / 2, shifted 26 periods ahead
        span_a = ((tenkan + kijun) / 2).shift(self.ichi_kijun)

        # Senkou Span B - 52 period mid, shifted 26 periods ahead
        high_52 = high.rolling(self.ichi_senkou_b).max()
        low_52 = low.rolling(self.ichi_senkou_b).min()
        span_b = ((high_52 + low_52) / 2).shift(self.ichi_kijun)

        return tenkan, kijun, span_a, span_b

    def add_indicators(self, df):
        """Add all 6 indicators to dataframe."""
        df = df.copy()

        # 1. SUPERTREND
        st_line, st_dir = self._calculate_supertrend(df)
        df['supertrend'] = st_line
        df['st_direction'] = st_dir

        # 2. HMA (Hull Moving Average)
        df['hma_fast'] = self._calculate_hma(df['Close'], self.hma_fast)
        df['hma_slow'] = self._calculate_hma(df['Close'], self.hma_slow)

        # 3. ADX + Directional Indicators
        adx_ind = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
        df['adx'] = adx_ind.adx()
        df['di_plus'] = adx_ind.adx_pos()
        df['di_minus'] = adx_ind.adx_neg()

        # 4. VWAP
        self._has_real_vwap = False
        if 'Volume' in df.columns and df['Volume'].sum() > 0:
            try:
                vwap = VolumeWeightedAveragePrice(
                    high=df['High'], low=df['Low'],
                    close=df['Close'], volume=df['Volume'], window=14
                )
                df['vwap'] = vwap.volume_weighted_average_price()
                self._has_real_vwap = True
            except Exception:
                df['vwap'] = df['Close']
        else:
            df['vwap'] = df['Close']

        # 5. MACD
        macd = MACD(
            df['Close'],
            window_slow=self.macd_slow,
            window_fast=self.macd_fast,
            window_sign=self.macd_signal_period
        )
        df['macd_line'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_hist'] = macd.macd_diff()

        # 6. ICHIMOKU CLOUD
        tenkan, kijun, span_a, span_b = self._calculate_ichimoku(df)
        df['ichi_tenkan'] = tenkan
        df['ichi_kijun'] = kijun
        df['ichi_span_a'] = span_a
        df['ichi_span_b'] = span_b

        # Supplementary: RSI
        df['rsi'] = RSIIndicator(df['Close'], window=self.rsi_period).rsi()

        # ATR for risk sizing
        df['atr'] = AverageTrueRange(
            df['High'], df['Low'], df['Close'], window=14
        ).average_true_range()

        return df

    # =========================================================
    # CONFLUENCE SCORING
    # =========================================================

    def _score_confluence(self, row, direction):
        """
        Score indicator confluence for entry.
        Returns (score, max_possible, indicator_names, details).

        For BUY, checks:
        1. Supertrend bullish (price above ST line)
        2. HMA fast > slow (upward momentum)
        3. Price > VWAP (institutional bullish)
        4. MACD histogram > 0 (bullish momentum)
        5. Price above Ichimoku cloud
        6. DI+ > DI- (directional movement)

        For SELL: mirror conditions.
        """
        score = 0
        max_score = 6
        details = []
        indicators_used = []
        current_price = row['Close']

        is_buy = (direction == "BUY")

        # 1. SUPERTREND
        st_bullish = (row['st_direction'] == 1)
        if (is_buy and st_bullish) or (not is_buy and not st_bullish):
            score += 1
            indicators_used.append("Supertrend")
            details.append(f"✅ Supertrend {'BULLISH' if is_buy else 'BEARISH'}")
        else:
            details.append(f"❌ Supertrend {'bearish' if is_buy else 'bullish'}")

        # 2. HMA CROSSOVER
        hma_f = row.get('hma_fast')
        hma_s = row.get('hma_slow')
        if not pd.isna(hma_f) and not pd.isna(hma_s):
            hma_aligned = (hma_f > hma_s) if is_buy else (hma_f < hma_s)
            if hma_aligned:
                score += 1
                indicators_used.append("HMA")
                details.append(f"✅ HMA Fast {'>' if is_buy else '<'} Slow")
            else:
                details.append(f"❌ HMA Fast {'<' if is_buy else '>'} Slow")
        else:
            max_score -= 1
            details.append("⬜ HMA N/A")

        # 3. VWAP
        if self._has_real_vwap:
            vwap_aligned = (current_price > row['vwap']) if is_buy else (current_price < row['vwap'])
            if vwap_aligned:
                score += 1
                indicators_used.append("VWAP")
                details.append(f"✅ Price {'>' if is_buy else '<'} VWAP")
            else:
                details.append(f"❌ Price {'<' if is_buy else '>'} VWAP")
        else:
            max_score -= 1
            details.append("⬜ VWAP N/A (no volume)")

        # 4. MACD HISTOGRAM
        macd_h = row.get('macd_hist')
        if not pd.isna(macd_h):
            macd_aligned = (macd_h > 0) if is_buy else (macd_h < 0)
            if macd_aligned:
                score += 1
                indicators_used.append("MACD")
                details.append(f"✅ MACD Hist {'> 0' if is_buy else '< 0'}")
            else:
                details.append(f"❌ MACD Hist {'< 0' if is_buy else '> 0'}")
        else:
            max_score -= 1
            details.append("⬜ MACD N/A")

        # 5. ICHIMOKU CLOUD
        span_a = row.get('ichi_span_a')
        span_b = row.get('ichi_span_b')
        if not pd.isna(span_a) and not pd.isna(span_b):
            cloud_top = max(span_a, span_b)
            cloud_bottom = min(span_a, span_b)
            if is_buy:
                if current_price > cloud_top:
                    score += 1
                    indicators_used.append("Ichimoku")
                    details.append("✅ Price above Ichimoku Cloud")
                else:
                    details.append("❌ Price inside/below Cloud")
            else:
                if current_price < cloud_bottom:
                    score += 1
                    indicators_used.append("Ichimoku")
                    details.append("✅ Price below Ichimoku Cloud")
                else:
                    details.append("❌ Price inside/above Cloud")
        else:
            max_score -= 1
            details.append("⬜ Ichimoku N/A (insufficient data)")

        # 6. DIRECTIONAL INDICATOR (DI+/DI-)
        di_p = row.get('di_plus')
        di_m = row.get('di_minus')
        if not pd.isna(di_p) and not pd.isna(di_m):
            di_aligned = (di_p > di_m) if is_buy else (di_m > di_p)
            if di_aligned:
                score += 1
                indicators_used.append("DI")
                details.append(f"✅ {'DI+ > DI-' if is_buy else 'DI- > DI+'}")
            else:
                details.append(f"❌ {'DI+ < DI-' if is_buy else 'DI- < DI+'}")
        else:
            max_score -= 1
            details.append("⬜ DI N/A")

        return score, max_score, indicators_used, details

    # =========================================================
    # SIGNAL GENERATION
    # =========================================================

    def get_signal(self, df, config=None, major_trend="NEUTRAL"):
        """
        Get trading signal with 6-indicator confluence scoring.

        Entry requires:
        1. ADX > 25 (baseline gate)
        2. Supertrend direction (primary)
        3. Confirmation candle
        4. Multi-timeframe alignment (4H)
        5. Minimum 3 of 6 indicators aligned

        SL: Supertrend level (dynamic, ATR-based)
        TP: 2.0x risk distance (R:R >= 1:2.0)
        """
        if len(df) < 100:
            return {
                "signal": "NEUTRAL", "confidence": 0,
                "reason": "Insufficient data (<100 bars)", "rsi": 50
            }

        df = self.add_indicators(df)

        row = df.iloc[-1]
        prev = df.iloc[-2]

        current_price = row['Close']
        adx = row['adx']
        rsi = row['rsi']
        atr = row['atr']
        supertrend = row['supertrend']
        st_dir = row['st_direction']

        # Guard: missing critical indicators
        if pd.isna(adx) or pd.isna(rsi) or pd.isna(atr) or pd.isna(supertrend):
            return {
                "signal": "NEUTRAL", "confidence": 0,
                "reason": "Missing critical indicators",
                "rsi": rsi if not pd.isna(rsi) else 50
            }

        # =============================================
        # GATE 1: ADX TREND STRENGTH (Required)
        # =============================================
        if adx < self.adx_min:
            return {
                "signal": "NEUTRAL", "confidence": 0,
                "reason": f"Weak trend (ADX {adx:.1f} < {self.adx_min})",
                "rsi": rsi, "adx": adx
            }

        # =============================================
        # GATE 2: SUPERTREND DIRECTION (Primary)
        # =============================================
        potential_direction = "BUY" if st_dir == 1 else "SELL"

        # =============================================
        # GATE 3: CONFIRMATION CANDLE
        # =============================================
        prev_bullish = prev['Close'] > prev['Open']
        prev_bearish = prev['Close'] < prev['Open']

        if potential_direction == "BUY" and not prev_bullish:
            return {
                "signal": "NEUTRAL", "confidence": 0,
                "reason": "Waiting for bullish confirmation candle",
                "rsi": rsi, "adx": adx
            }
        if potential_direction == "SELL" and not prev_bearish:
            return {
                "signal": "NEUTRAL", "confidence": 0,
                "reason": "Waiting for bearish confirmation candle",
                "rsi": rsi, "adx": adx
            }

        # =============================================
        # GATE 4: MULTI-TIMEFRAME ALIGNMENT
        # =============================================
        if major_trend != "NEUTRAL":
            if potential_direction == "BUY" and major_trend == "DOWN":
                return {
                    "signal": "NEUTRAL", "confidence": 0,
                    "reason": f"MTF conflict: BUY signal vs 4H DOWN trend",
                    "rsi": rsi, "adx": adx
                }
            if potential_direction == "SELL" and major_trend == "UP":
                return {
                    "signal": "NEUTRAL", "confidence": 0,
                    "reason": f"MTF conflict: SELL signal vs 4H UP trend",
                    "rsi": rsi, "adx": adx
                }

        # =============================================
        # GATE 5: CONFLUENCE SCORING (Min 3 of 6)
        # =============================================
        score, max_score, indicators_used, details = self._score_confluence(
            row, potential_direction
        )

        min_required = min(self.min_confluence, max_score)

        if score < min_required:
            return {
                "signal": "NEUTRAL", "confidence": 0,
                "reason": f"Low confluence ({score}/{max_score}, need {min_required})",
                "rsi": rsi, "adx": adx,
                "filters": details
            }

        # =============================================
        # CALCULATE SL/TP (Supertrend-based)
        # =============================================
        # SL at Supertrend level (dynamic ATR-based trailing stop)
        sl = supertrend
        if potential_direction == "BUY":
            risk = current_price - sl
        else:
            risk = sl - current_price

        # Minimum SL distance = 1.0 * ATR (avoid tiny stops)
        min_risk = atr * 1.0
        if risk < min_risk:
            if potential_direction == "BUY":
                sl = current_price - min_risk
            else:
                sl = current_price + min_risk
            risk = min_risk

        # Maximum SL distance = 3.0% of price
        max_risk = current_price * 0.03
        if risk > max_risk:
            if potential_direction == "BUY":
                sl = current_price - max_risk
            else:
                sl = current_price + max_risk
            risk = max_risk

        # TP at R:R ratio from SL
        if potential_direction == "BUY":
            tp = current_price + (risk * self.min_rr_ratio)
        else:
            tp = current_price - (risk * self.min_rr_ratio)

        # Validate R:R (with small tolerance for floating point)
        actual_rr = abs(tp - current_price) / abs(current_price - sl) if abs(current_price - sl) > 0 else 0
        if actual_rr < self.min_rr_ratio - 0.01:
            return {
                "signal": "NEUTRAL", "confidence": 0,
                "reason": f"R:R {actual_rr:.2f} < {self.min_rr_ratio}",
                "rsi": rsi, "adx": adx
            }

        # =============================================
        # CONFIDENCE CALCULATION
        # =============================================
        # Base: 0.55, scales with confluence and ADX strength
        confidence = 0.55 + (score / max(max_score, 1)) * 0.35
        confidence += (adx - self.adx_min) / 300  # ADX strength boost
        confidence = min(0.95, max(0.55, confidence))

        # =============================================
        # BUILD RESULT
        # =============================================
        # Smart rounding
        if current_price < 10:
            decimals = 5
        elif current_price < 1000:
            decimals = 2
        else:
            decimals = 1

        reason = (
            f"TREND {potential_direction}: "
            f"Confluence {score}/{max_score}, "
            f"ADX {adx:.1f}, R:R {actual_rr:.1f}"
        )

        # Prepend summary to filter details
        details.insert(0, f"📊 ADX: {adx:.1f} (Strong Trend)")
        details.insert(1, f"🎯 Confluence: {score}/{max_score}")
        details.insert(2, f"📐 R:R: {actual_rr:.2f}")
        if major_trend != "NEUTRAL":
            details.insert(3, f"📈 4H Trend: {major_trend}")

        return {
            "signal": potential_direction,
            "confidence": round(confidence, 3),
            "sl": round(sl, decimals),
            "tp": round(tp, decimals),
            "rsi": rsi,
            "adx": adx,
            "reason": reason,
            "filters": details,
            "strategy": "TREND_2026",
            "confluence_score": score,
            "confluence_max": max_score,
            "indicators_used": indicators_used,
            "supertrend_level": round(supertrend, decimals),
        }


# Singleton
_strategy_instance = None

def get_strategy(config=None):
    global _strategy_instance
    if _strategy_instance is None:
        _strategy_instance = TrendStrategy(config)
    return _strategy_instance


if __name__ == "__main__":
    import yfinance as yf

    print("Testing Trend Strategy v2.0 (2026 Guide)")
    print("=" * 60)

    tickers = ["EURUSD=X", "BTC-USD", "NVDA", "GBPUSD=X"]
    strategy = TrendStrategy()

    for ticker in tickers:
        try:
            data = yf.download(ticker, period="1mo", interval="1h", progress=False)
            if hasattr(data.columns, 'levels'):
                data.columns = data.columns.get_level_values(0)
            if len(data) < 100:
                print(f"\n{ticker}: Insufficient data ({len(data)} bars)")
                continue

            signal = strategy.get_signal(data)

            print(f"\n{ticker}:")
            print(f"  Signal: {signal['signal']}")
            print(f"  Confidence: {signal.get('confidence', 0):.2f}")
            print(f"  RSI: {signal.get('rsi', 0):.1f}")
            print(f"  ADX: {signal.get('adx', 0):.1f}")
            print(f"  Reason: {signal.get('reason', '')}")

            if signal.get('filters'):
                print("  Filters:")
                for f in signal['filters']:
                    print(f"    {f}")

            if signal.get('indicators_used'):
                print(f"  Indicators: {', '.join(signal['indicators_used'])}")

        except Exception as e:
            print(f"\n{ticker}: Error - {e}")

    print("\n" + "=" * 60)
    print("Test complete!")
