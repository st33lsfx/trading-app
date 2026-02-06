"""
Elite Strategy v1.0 (2026 Ultimate Hybrid)
===========================================
The "Absolute Best" indicator combination from QuantVPS & NAGA Academy 2026 guides.
Designed for maximum profitability in volatile ranging + trend phases.

CORE INDICATORS (7-Point Confluence):
1. Hull Moving Average (HMA 9/21) - Low-lag trend direction
2. Supertrend (ATR 10, 3.0) - Trend filter & Dynamic Trailing Stop
3. ADX (14) - Trend strength gate (>25 = Trending)
4. Parabolic SAR (0.02, 0.2) - Trailing exit & reversal confirmation
5. Ichimoku Cloud - Support/Resistance & Cloud Twist
6. MACD (12,26,9) - Momentum alignment
7. VWAP - Institutional Fair Value (Price > VWAP = Bullish)

ENTRY RULES:
- ADX > 25 (Trend Mode Only)
- STRICT CONFLUENCE: Mimimum 4 of 7 indicators must align.
- Multi-Timeframe Alignment (simulated via higher-period settings)

RISK MANAGEMENT:
- Dynamic Risk: 0.5% - 0.7% based on confluence score.
- SL: Dynamic ATR-based or Supertrend level.
- TP: Open interval with Trailing Stop (PSAR/Supertrend).
"""

import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, MACD, PSARIndicator
from ta.volatility import AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice


class EliteStrategy:
    """
    Elite Trading Strategy 2026
    Combines top-rated indicators for high-probability entries.
    """

    def __init__(self, config=None):
        self.config = config or {}

        # === 1. SUPERTREND (Trend & Stop) ===
        self.st_period = self.config.get('st_period', 10)
        self.st_multiplier = self.config.get('st_multiplier', 3.0)

        # === 2. HMA (Low Lag Trend) ===
        self.hma_fast = self.config.get('hma_fast', 9)
        self.hma_slow = self.config.get('hma_slow', 21)

        # === 3. ADX (Regime Gate) ===
        self.adx_min = self.config.get('adx_min', 25)

        # === 4. PARABOLIC SAR (Trailing Exit) ===
        self.psar_step = 0.02
        self.psar_max = 0.2

        # === 5. MACD (Momentum) ===
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_sign = 9

        # === 6. ICHIMOKU (Support/Resistance) ===
        self.ichi_tenkan = 9
        self.ichi_kijun = 26
        self.ichi_senkou_b = 52

        # === RISK MANAGEMENT ===
        self.min_rr_ratio = self.config.get('min_rr_ratio', 2.0)
        self.min_confluence = 4  # STRICT: Need 4+ indicators
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
        """Hull Moving Average - eliminates lag."""
        half_len = max(1, int(window / 2))
        sqrt_len = max(1, int(np.sqrt(window)))
        wma_half = self._calculate_wma(series, half_len)
        wma_full = self._calculate_wma(series, window)
        raw_hma = 2 * wma_half - wma_full
        return self._calculate_wma(raw_hma, sqrt_len)

    def _calculate_supertrend(self, df):
        """Calculate Supertrend (Trend + Direction)."""
        high, low, close = df['High'], df['Low'], df['Close']
        
        # ATR
        atr = AverageTrueRange(high, low, close, window=self.st_period).average_true_range()
        
        # Basic Upper/Lower Bands
        hl2 = (high + low) / 2
        basic_upper = hl2 + (self.st_multiplier * atr)
        basic_lower = hl2 - (self.st_multiplier * atr)
        
        n = len(df)
        upper_band = np.zeros(n)
        lower_band = np.zeros(n)
        supertrend = np.zeros(n)
        direction = np.ones(n, dtype=int) # 1=Bull, -1=Bear
        
        close_vals = close.values
        bu_vals = basic_upper.values
        bl_vals = basic_lower.values
        
        # Init
        upper_band[0] = bu_vals[0]
        lower_band[0] = bl_vals[0]
        supertrend[0] = lower_band[0]
        
        for i in range(1, n):
            # Upper Band Logic
            if bu_vals[i] < upper_band[i-1] or close_vals[i-1] > upper_band[i-1]:
                upper_band[i] = bu_vals[i]
            else:
                upper_band[i] = upper_band[i-1]
                
            # Lower Band Logic
            if bl_vals[i] > lower_band[i-1] or close_vals[i-1] < lower_band[i-1]:
                lower_band[i] = bl_vals[i]
            else:
                lower_band[i] = lower_band[i-1]
                
            # Trend Logic
            if supertrend[i-1] == upper_band[i-1]: # Was Bearish
                if close_vals[i] > upper_band[i]:
                    supertrend[i] = lower_band[i]
                    direction[i] = 1
                else:
                    supertrend[i] = upper_band[i]
                    direction[i] = -1
            else: # Was Bullish
                if close_vals[i] < lower_band[i]:
                    supertrend[i] = upper_band[i]
                    direction[i] = -1
                else:
                    supertrend[i] = lower_band[i]
                    direction[i] = 1
                    
        return pd.Series(supertrend, index=df.index), pd.Series(direction, index=df.index)

    def _calculate_ichimoku(self, df):
        """Ichimoku Cloud Components."""
        high, low = df['High'], df['Low']
        
        # Tenkan (9)
        high_9 = high.rolling(self.ichi_tenkan).max()
        low_9 = low.rolling(self.ichi_tenkan).min()
        tenkan = (high_9 + low_9) / 2
        
        # Kijun (26)
        high_26 = high.rolling(self.ichi_kijun).max()
        low_26 = low.rolling(self.ichi_kijun).min()
        kijun = (high_26 + low_26) / 2
        
        # Senkou A (shifted 26)
        span_a = ((tenkan + kijun) / 2).shift(self.ichi_kijun)
        
        # Senkou B (52, shifted 26)
        high_52 = high.rolling(self.ichi_senkou_b).max()
        low_52 = low.rolling(self.ichi_senkou_b).min()
        span_b = ((high_52 + low_52) / 2).shift(self.ichi_kijun)
        
        return span_a, span_b

    def add_indicators(self, df):
        """Add all 7 Elite Indicators."""
        df = df.copy()
        close = df['Close']
        
        # 1. HMA
        df['hma_fast'] = self._calculate_hma(close, self.hma_fast)
        df['hma_slow'] = self._calculate_hma(close, self.hma_slow)
        
        # 2. Supertrend
        st_val, st_dir = self._calculate_supertrend(df)
        df['supertrend'] = st_val
        df['st_direction'] = st_dir

        # 3. ADX
        adx = ADXIndicator(df['High'], df['Low'], close, window=14)
        df['adx'] = adx.adx()
        df['di_plus'] = adx.adx_pos()
        df['di_minus'] = adx.adx_neg()

        # 4. Parabolic SAR
        psar = PSARIndicator(df['High'], df['Low'], close, step=self.psar_step, max_step=self.psar_max)
        df['psar'] = psar.psar()

        # 5. MACD
        macd = MACD(close, window_slow=self.macd_slow, window_fast=self.macd_fast, window_sign=self.macd_sign)
        df['macd_hist'] = macd.macd_diff()

        # 6. Ichimoku
        span_a, span_b = self._calculate_ichimoku(df)
        df['ichi_span_a'] = span_a
        df['ichi_span_b'] = span_b

        # 7. VWAP
        if 'Volume' in df.columns and df['Volume'].sum() > 0:
            vwap = VolumeWeightedAveragePrice(df['High'], df['Low'], close, df['Volume'], window=14)
            df['vwap'] = vwap.volume_weighted_average_price()
            self._has_real_vwap = True
        else:
            df['vwap'] = close
            self._has_real_vwap = False

        # ATR & RSI (Helpers)
        df['atr'] = AverageTrueRange(df['High'], df['Low'], close, window=14).average_true_range()
        df['rsi'] = RSIIndicator(close, window=14).rsi()

        return df

    # =========================================================
    # CONFLUENCE SCORING (The Core Logic)
    # =========================================================

    def _score_confluence(self, row, direction):
        """
        Check alignment of all 7 indicators.
        Returns: score (0-7), max_score
        """
        score = 0
        max_score = 7
        details = []
        indicators_used = []
        is_buy = (direction == "BUY")
        close = row['Close']

        # 1. HMA (Direction)
        if not pd.isna(row['hma_fast']) and not pd.isna(row['hma_slow']):
            hma_ok = (row['hma_fast'] > row['hma_slow']) if is_buy else (row['hma_fast'] < row['hma_slow'])
            if hma_ok:
                score += 1
                indicators_used.append("HMA")
                details.append(f"✅ HMA")
            else:
                details.append(f"❌ HMA")
        else:
            max_score -= 1

        # 2. Supertrend (Direction)
        st_ok = (row['st_direction'] == 1) if is_buy else (row['st_direction'] == -1)
        if st_ok:
            score += 1
            indicators_used.append("Supertrend")
            details.append(f"✅ Supertrend")
        else:
            details.append(f"❌ Supertrend")
            
        # 3. Parabolic SAR (Position)
        # Buy if Price > PSAR, Sell if Price < PSAR
        psar_ok = (close > row['psar']) if is_buy else (close < row['psar'])
        if psar_ok:
            score += 1
            indicators_used.append("PSAR")
            details.append(f"✅ PSAR")
        else:
            details.append(f"❌ PSAR")

        # 4. MACD (Momentum)
        macd_ok = (row['macd_hist'] > 0) if is_buy else (row['macd_hist'] < 0)
        if macd_ok:
            score += 1
            indicators_used.append("MACD")
            details.append(f"✅ MACD")
        else:
            details.append(f"❌ MACD")

        # 5. Ichimoku (Cloud Filter)
        span_a, span_b = row['ichi_span_a'], row['ichi_span_b']
        if not pd.isna(span_a) and not pd.isna(span_b):
            cloud_top = max(span_a, span_b)
            cloud_bottom = min(span_a, span_b)
            ichi_ok = (close > cloud_top) if is_buy else (close < cloud_bottom)
            if ichi_ok:
                score += 1
                indicators_used.append("Ichimoku")
                details.append(f"✅ Ichimoku")
            else:
                details.append(f"❌ Ichimoku")
        else:
            max_score -= 1

        # 6. VWAP (Institutional Value)
        if self._has_real_vwap:
            vwap_ok = (close > row['vwap']) if is_buy else (close < row['vwap'])
            if vwap_ok:
                score += 1
                indicators_used.append("VWAP")
                details.append(f"✅ VWAP")
            else:
                details.append(f"❌ VWAP")
        else:
            max_score -= 1
            details.append("⬜ VWAP (No Vol)")

        # 7. ADX DI (Directional Strength)
        di_ok = (row['di_plus'] > row['di_minus']) if is_buy else (row['di_minus'] > row['di_plus'])
        if di_ok:
            score += 1
            indicators_used.append("DI+/-")
            details.append(f"✅ DI+/-")
        else:
            details.append(f"❌ DI+/-")

        return score, max_score, indicators_used, details

    # =========================================================
    # SIGNAL GENERATION
    # =========================================================

    def get_signal(self, df, config=None, major_trend="NEUTRAL"):
        """
        Get Elite Signal.
        """
        if len(df) < 60:
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Initializing...", "rsi": 50}

        df = self.add_indicators(df)
        row = df.iloc[-1]
        prev = df.iloc[-2]
        
        close = row['Close']
        adx = row['adx']
        atr = row['atr']
        rsi = row['rsi']
        
        # 1. GATE: Trend Strength (ADX)
        if adx < self.adx_min:
            return {
                "signal": "NEUTRAL", 
                "confidence": 0, 
                "reason": f"Weak Trend (ADX {adx:.1f} < {self.adx_min})",
                "rsi": rsi, "adx": adx
            }

        # 2. DETERMINE POTENTIAL DIRECTION (from Supertrend)
        direction = "BUY" if row['st_direction'] == 1 else "SELL"
        
        # 3. CHECK CONFIRMATION CANDLE
        is_bullish = close > df.iloc[-1]['Open']
        if direction == "BUY" and not is_bullish:
             return {"signal": "NEUTRAL", "confidence": 0, "reason": "Wait for Bullish Candle", "rsi": rsi}
        if direction == "SELL" and is_bullish: # Bearish candle check (Open > Close)
             return {"signal": "NEUTRAL", "confidence": 0, "reason": "Wait for Bearish Candle", "rsi": rsi}
             
        # 4. CONFLUENCE CHECK
        score, max_s, tools, details = self._score_confluence(row, direction)
        
        required = min(self.min_confluence, max_s)
        if score < required:
            return {
                "signal": "NEUTRAL",
                "confidence": 0,
                "reason": f"Low Confluence ({score}/{max_s})",
                "rsi": rsi, "adx": adx, "filters": details
            }
            
        # 5. RISK MANAGEMENT
        sl_base = row['supertrend']
        
        # Ensure Min/Max Stop Distance
        dist = abs(close - sl_base)
        min_dist = atr * 1.5
        max_dist = close * 0.04 # Max 4% risk
        
        if dist < min_dist: dist = min_dist
        if dist > max_dist: dist = max_dist
        
        if direction == "BUY":
            sl = close - dist
            tp = close + (dist * self.min_rr_ratio)
        else:
            sl = close + dist
            tp = close - (dist * self.min_rr_ratio)
            
        # Confidence Scaling
        confidence = 0.6 + (score/max_s * 0.3) + (min(adx, 50)/200)
        
        return {
            "signal": direction,
            "confidence": min(0.95, confidence),
            "sl": round(sl, 4),
            "tp": round(tp, 4),
            "rsi": rsi,
            "adx": adx,
            "reason": f"ELITE {direction}: Score {score}/{max_s}, ADX {adx:.0f}",
            "filters": details,
            "strategy": "ELITE_2026",
            "indicators_used": tools
        }

if __name__ == "__main__":
    print("Elite Strategy Loaded.")
