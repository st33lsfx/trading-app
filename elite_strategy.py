"""
Elite Strategie v3.3 (2026 Ultimate Volume Profile Core - Final Live Deploy)
=============================================================================
Designed for the "Elite 15" Asset List on Capital.com.
Core Edge: Volume Profile (VP) + VWAP + Confluence.

REGIMES:
1. TREND (ADX > 25):
   - Breakout of Value Area (VAH/VAL) with Volume Spike.
   - Pullback to POC/VWAP in established trend.
   - Targets: Next LVN (Low Volume Node) or ATR multiple.

2. RANGE (ADX < 25):
   - Reversal at Value Area High (VAH) -> Target POC.
   - Reversal at Value Area Low (VAL) -> Target POC.
   - Confirmation: RSI Divergence / MACD / Rejection Candle.

STRICT CONFLUENCE RULES:
- VP Signal is MANDATORY (must interact with VAH/VAL/POC).
- Minimum 3 other indicators must align (Total 4+).
"""

import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, MACD, PSARIndicator
from ta.volatility import AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice

class EliteStrategy:
    """
    Elite Trading Strategy 3.3 (Volume Profile Centered + Asset-Class Risk)

    v3.3 Changes (Final Live Deploy):
    - Crypto: ATR×5.5 SL / ATR×12.0 TP — wider for trend continuation
    - Forex: ATR×3.0 SL / ATR×6.0 TP — room to breathe
    - Partial close schedule: 40% @ 1.5R, 30% @ 2.0R, rest trails
    - Adaptive trailing with Supertrend + ATR buffer after 1:1
    - Enhanced signal output with volatility context
    """

    # === ASSET CLASS RISK PROFILES (v3.3 - Final Optimized) ===
    RISK_PROFILES = {
        "crypto": {
            "atr_sl_mult": 5.5,       # v3.3: Wider SL (was 5.0) — better wick survival
            "atr_tp_mult": 12.0,      # v3.3: TP at 12× ATR (was 10.0) — lets trends run
            "min_sl_pct": 0.02,       # Min 2.0% SL — crypto needs room
            "max_sl_pct": 0.07,       # v3.3: Maximum 7% SL distance (was 6%)
            "min_rr": 2.0,            # Minimum R:R
        },
        "forex": {
            "atr_sl_mult": 3.0,       # v3.3: Wider SL (was 2.5) — avoids premature stops
            "atr_tp_mult": 6.0,       # v3.3: TP at 6.0× ATR (was 5.5) — wider targets
            "min_sl_pct": 0.004,      # Minimum 0.4% SL (≈40 pips on majors)
            "max_sl_pct": 0.025,      # Maximum 2.5%
            "min_rr": 2.0,
        },
        "default": {
            "atr_sl_mult": 3.0,
            "atr_tp_mult": 6.0,
            "min_sl_pct": 0.008,
            "max_sl_pct": 0.04,
            "min_rr": 2.0,
        }
    }

    # === PARTIAL CLOSE SCHEDULE (v3.3) ===
    PARTIAL_SCHEDULE = [
        {"r_mult": 1.5, "close_pct": 0.40, "label": "Partial-1 @ 1.5R (40%)"},
        {"r_mult": 2.0, "close_pct": 0.30, "label": "Partial-2 @ 2.0R (30%)"},
        # Remaining 30% trails with Supertrend + ATR buffer
    ]

    # === TRAILING STOP LEVELS (v3.3 - Adaptive) ===
    TRAIL_LEVELS = [
        {"r_mult": 1.0, "lock_r": 0.0,  "label": "Breakeven"},
        {"r_mult": 1.5, "lock_r": 0.5,  "label": "Lock 0.5R"},
        {"r_mult": 2.0, "lock_r": 1.0,  "label": "Lock 1.0R"},
        {"r_mult": 3.0, "lock_r": 1.5,  "label": "Lock 1.5R"},
        {"r_mult": 4.0, "lock_r": 2.5,  "label": "Lock 2.5R"},
    ]

    def __init__(self, config=None):
        self.config = config or {}

        # === 1. VOLUME PROFILE (The Core) ===
        self.vp_bins = 24       # Granularity
        self.vp_lookback = 70   # Candles for VP calculation (approx 2 days on 15m)

        # === 2. TREND / REGIME ===
        self.adx_min = 25       # Regime boundary
        self.hma_fast = 9
        self.hma_slow = 21
        self.st_period = 10
        self.st_multiplier = 3.0

        # === 3. MOMENTUM / CONFIRMATION ===
        self.rsi_period = 14
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_sign = 9

        # === 4. EXITS ===
        self.psar_step = 0.02
        self.psar_max = 0.2

        # === RISK MANAGEMENT ===
        self.min_rr_ratio = self.config.get('min_rr_ratio', 2.0)
        self.min_confluence = self.config.get('min_confluence', 4)  # VP + 3 others
        self.atr_sl_mult = self.config.get('atr_sl_mult', 2.0)  # Base fallback (overridden by asset class)

        # Internal state
        self._has_real_vwap = False

    # =========================================================
    # INDICATOR CALCULATIONS
    # =========================================================

    def _calculate_wma(self, series, window):
        weights = np.arange(1, window + 1)
        return series.rolling(window).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

    def _calculate_hma(self, series, window):
        half_len = max(1, int(window / 2))
        sqrt_len = max(1, int(np.sqrt(window)))
        wma_half = self._calculate_wma(series, half_len)
        wma_full = self._calculate_wma(series, window)
        raw_hma = 2 * wma_half - wma_full
        return self._calculate_wma(raw_hma, sqrt_len)

    def _calculate_supertrend(self, df):
        high, low, close = df['High'], df['Low'], df['Close']
        atr = AverageTrueRange(high, low, close, window=self.st_period).average_true_range()
        
        hl2 = (high + low) / 2
        basic_upper = hl2 + (self.st_multiplier * atr)
        basic_lower = hl2 - (self.st_multiplier * atr)
        
        n = len(df)
        upper_band = np.zeros(n)
        lower_band = np.zeros(n)
        supertrend = np.zeros(n)
        direction = np.ones(n, dtype=int) # 1=Bull, -1=Bear
        
        # Vectorized-like loop (optimized)
        # Initialization
        upper_band[0] = basic_upper.iloc[0]
        lower_band[0] = basic_lower.iloc[0]
        supertrend[0] = lower_band[0]
        
        for i in range(1, n):
            # Upper
            if basic_upper.iloc[i] < upper_band[i-1] or close.iloc[i-1] > upper_band[i-1]:
                upper_band[i] = basic_upper.iloc[i]
            else:
                upper_band[i] = upper_band[i-1]
            
            # Lower
            if basic_lower.iloc[i] > lower_band[i-1] or close.iloc[i-1] < lower_band[i-1]:
                lower_band[i] = basic_lower.iloc[i]
            else:
                lower_band[i] = lower_band[i-1]
                
            # Trend
            if supertrend[i-1] == upper_band[i-1]: # Was Bearish
                if close.iloc[i] > upper_band[i]:
                    supertrend[i] = lower_band[i]
                    direction[i] = 1
                else:
                    supertrend[i] = upper_band[i]
                    direction[i] = -1
            else: # Was Bullish
                if close.iloc[i] < lower_band[i]:
                    supertrend[i] = upper_band[i]
                    direction[i] = -1
                else:
                    supertrend[i] = lower_band[i]
                    direction[i] = 1
                    
        return pd.Series(supertrend, index=df.index), pd.Series(direction, index=df.index)

    def _calculate_volume_profile(self, df):
        """
        Advanced VP: POC, VAH, VAL, and High/Low Volume Nodes.
        """
        if 'Volume' not in df.columns:
            return None
            
        # FIX FOR FOREX (Yahoo has 0 vol): Use Volatility as Volume Proxy
        if df['Volume'].sum() == 0:
            vol_proxy = (df['High'] - df['Low']) * 100000
            df = df.copy()
            df['Volume'] = vol_proxy
            
        lookback = min(len(df), self.vp_lookback)
        subset = df.tail(lookback)
        
        price_min = subset['Close'].min()
        price_max = subset['Close'].max()
        if price_min == price_max: return None
        
        range_size = price_max - price_min
        bin_size = range_size / self.vp_bins
        
        # 1. Bucket Volume
        bins = {}
        for idx, row in subset.iterrows():
            p = row['Close']
            v = row['Volume']
            bin_idx = int((p - price_min) / bin_size)
            bins[bin_idx] = bins.get(bin_idx, 0) + v
            
        if not bins: return None

        # 2. Find POC
        poc_bin = max(bins, key=bins.get)
        poc_price = price_min + (poc_bin + 0.5) * bin_size
        
        # 3. Value Area (70%)
        total_vol = sum(bins.values())
        sorted_bins = sorted(bins.items(), key=lambda x: x[1], reverse=True)
        
        va_vol = 0
        va_bins = []
        for b_idx, vol in sorted_bins:
            va_vol += vol
            va_bins.append(b_idx)
            if va_vol >= total_vol * 0.70:
                break
                
        va_high = price_min + (max(va_bins) + 1) * bin_size
        va_low = price_min + min(va_bins) * bin_size
        
        return {
            "poc": poc_price,
            "vah": va_high,
            "val": va_low,
            "total_vol": total_vol,
            "bins": bins, # For LVN analysis
            "bin_size": bin_size,
            "min_price": price_min
        }

    def _find_targets_using_vp(self, close, direction, vp_data):
        """Find next LVN (Low Volume Node) as target."""
        if not vp_data: return None
        
        bins = vp_data['bins']
        bin_size = vp_data['bin_size']
        min_price = vp_data['min_price']
        current_bin = int((close - min_price) / bin_size)
        
        # Find next significant drop in volume (LVN)
        sorted_keys = sorted(bins.keys())
        target_price = None
        
        if direction == "BUY":
            # Search upwards
            for b in sorted_keys:
                if b > current_bin:
                    vol = bins.get(b, 0)
                    avg_vol = vp_data['total_vol'] / len(bins)
                    if vol < (avg_vol * 0.5): # LVN detected
                        target_price = min_price + (b + 0.5) * bin_size
                        break
        else:
            # Search downwards
            for b in sorted_keys[::-1]:
                 if b < current_bin:
                    vol = bins.get(b, 0)
                    avg_vol = vp_data['total_vol'] / len(bins)
                    if vol < (avg_vol * 0.5): # LVN detected
                        target_price = min_price + (b + 0.5) * bin_size
                        break
        
        return target_price

    def add_indicators(self, df):
        df = df.copy()
        close = df['Close']
        
        # HMA
        df['hma_fast'] = self._calculate_hma(close, self.hma_fast)
        df['hma_slow'] = self._calculate_hma(close, self.hma_slow)
        
        # Supertrend
        st_val, st_dir = self._calculate_supertrend(df)
        df['supertrend'] = st_val
        df['st_direction'] = st_dir

        # ADX
        adx_ind = ADXIndicator(df['High'], df['Low'], close, window=14)
        df['adx'] = adx_ind.adx()
        df['di_plus'] = adx_ind.adx_pos()
        df['di_minus'] = adx_ind.adx_neg()

        # PSAR
        psar = PSARIndicator(df['High'], df['Low'], close, step=self.psar_step, max_step=self.psar_max)
        df['psar'] = psar.psar()

        # MACD
        macd = MACD(close, window_slow=self.macd_slow, window_fast=self.macd_fast, window_sign=self.macd_sign)
        df['macd_hist'] = macd.macd_diff()

        # VWAP
        if 'Volume' in df.columns and df['Volume'].sum() > 0:
            vwap = VolumeWeightedAveragePrice(df['High'], df['Low'], close, df['Volume'], window=14)
            df['vwap'] = vwap.volume_weighted_average_price()
            self._has_real_vwap = True
        else:
            df['vwap'] = close
            self._has_real_vwap = False

        # ATR & RSI
        df['atr'] = AverageTrueRange(df['High'], df['Low'], close, window=14).average_true_range()
        df['rsi'] = RSIIndicator(close, window=14).rsi()

        return df

    # =========================================================
    # CONFLUENCE SCORING
    # =========================================================

    def _score_confluence(self, row, direction, regime):
        """
        Calculates confluence score. VP IS MANDATORY via get_signal logic.
        This scores the *supporting* indicators.
        """
        score = 0
        max_score = 6 # VWAP, HMA, ST, MACD, PSAR, RSI
        details = []
        indicators_used = []
        is_buy = (direction == "BUY")
        close = row['Close']

        # 1. VWAP (Important)
        if self._has_real_vwap:
            vwap_ok = (close > row['vwap']) if is_buy else (close < row['vwap'])
            if vwap_ok:
                score += 1
                indicators_used.append("VWAP")
                details.append("✅ VWAP")
            else:
                details.append("❌ VWAP")
        else:
            max_score -= 1

        # 2. HMA (Trend)
        hma_ok = (row['hma_fast'] > row['hma_slow']) if is_buy else (row['hma_fast'] < row['hma_slow'])
        if hma_ok:
            score += 1
            indicators_used.append("HMA")
            details.append("✅ HMA")
        else:
            details.append("❌ HMA")

        # 3. Supertrend
        st_ok = (row['st_direction'] == 1) if is_buy else (row['st_direction'] == -1)
        if st_ok:
            score += 1
            indicators_used.append("Supertrend")
            details.append("✅ Supertrend")
        else:
            details.append("❌ Supertrend")

        # 4. MACD
        macd_ok = (row['macd_hist'] > 0) if is_buy else (row['macd_hist'] < 0)
        if macd_ok:
            score += 1
            indicators_used.append("MACD")
            details.append("✅ MACD")

        # 5. RSI (Regime Dependent)
        if regime == "TREND":
            # In trend, RSI should not be over-cooked AGAINST us
            rsi_ok = (row['rsi'] < 70) if is_buy else (row['rsi'] > 30)
        else:
            # In range, RSI should favor mean reversion (reversal from extremes)
            # Buy signal (at VAL) needs RSI turning up from low
            rsi_ok = (row['rsi'] < 45) if is_buy else (row['rsi'] > 55)
            
        if rsi_ok:
            score += 1
            details.append("✅ RSI")

        # 6. PSAR
        psar_ok = (close > row['psar']) if is_buy else (close < row['psar'])
        if psar_ok:
            score += 1
            details.append("✅ PSAR")

        return score, max_score, indicators_used, details

    # =========================================================
    # CORE SIGNAL LOGIC
    # =========================================================

    def _get_risk_profile(self, asset_class):
        """Get risk profile for asset class."""
        return self.RISK_PROFILES.get(asset_class, self.RISK_PROFILES["default"])

    def _detect_asset_class_from_data(self, df):
        """Fallback asset class detection from price characteristics."""
        close = df['Close'].iloc[-1]
        if close > 500:  # Crypto (BTC, ETH) or expensive stock
            return "crypto"
        elif close < 10:  # Forex pairs (0.6 - 1.5 range mostly)
            return "forex"
        return "default"

    def get_signal(self, df, asset_class=None):
        if len(df) < 60:
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Init..."}

        # Optimization: Skip indicator recalc if already present
        if 'hma_fast' not in df.columns:
            df = self.add_indicators(df)

        row = df.iloc[-1]
        close = row['Close']
        adx = row['adx']
        atr = row['atr']

        # Auto-detect asset class if not provided
        if not asset_class:
            asset_class = self._detect_asset_class_from_data(df)

        risk = self._get_risk_profile(asset_class)

        # 1. DETERMINE REGIME
        regime = "TREND" if adx > self.adx_min else "RANGE"

        # 2. CALCULATE VP
        vp = self._calculate_volume_profile(df)
        if not vp:
            return {"signal": "NEUTRAL", "reason": "No Volume Data"}

        poc, vah, val = vp['poc'], vp['vah'], vp['val']

        # 3. IDENTIFY SIGNAL CANDIDATE (VP Centered)
        signal_candidate = "NEUTRAL"
        vp_reason = ""

        # === TREND LOGIC (Breakouts & Pullbacks) ===
        if regime == "TREND":
            if close > vah:
                signal_candidate = "BUY"
                vp_reason = "VP: Breakout > VAH"
            elif close > poc and row['st_direction'] == 1:
                signal_candidate = "BUY"
                vp_reason = "VP: Trend > POC"
            elif close < val:
                signal_candidate = "SELL"
                vp_reason = "VP: Breakout < VAL"
            elif close < poc and row['st_direction'] == -1:
                signal_candidate = "SELL"
                vp_reason = "VP: Trend < POC"

        # === RANGE LOGIC (Reversals at Value Area Edges) ===
        else:
            dist_to_val = abs(close - val) / close
            if close > val and dist_to_val < 0.005:
                signal_candidate = "BUY"
                vp_reason = "VP: Range Reversal @ VAL"

            dist_to_vah = abs(close - vah) / close
            if close < vah and dist_to_vah < 0.005:
                signal_candidate = "SELL"
                vp_reason = "VP: Range Reversal @ VAH"

        if signal_candidate == "NEUTRAL":
            return {"signal": "NEUTRAL", "confidence": 0, "reason": f"{regime}: No VP Trigger", "adx": adx, "rsi": row.get('rsi', 50)}

        # 4. STRICT CONFLUENCE CHECK
        score, max_s, tools, details = self._score_confluence(row, signal_candidate, regime)

        tools.append("VolProfile")

        req_score = 3

        if score < req_score:
             return {
                "signal": "NEUTRAL",
                "confidence": 0,
                "reason": f"Low Confluence ({score}/{max_s} extra)",
                "filters": details,
                "vp_context": vp_reason,
                "rsi": row.get('rsi', 50),
            }

        # 5. CONFIRMATION CANDLE check
        is_bullish = close > df.iloc[-1]['Open']
        if signal_candidate == "BUY" and not is_bullish:
             return {"signal": "NEUTRAL", "reason": "Wait for Green Candle", "rsi": row.get('rsi', 50)}
        if signal_candidate == "SELL" and is_bullish:
             return {"signal": "NEUTRAL", "reason": "Wait for Red Candle", "rsi": row.get('rsi', 50)}

        # =========================================================
        # 6. ASSET-CLASS-AWARE SL/TP CALCULATION (v3.1 FIX)
        # =========================================================
        atr_sl_mult = risk["atr_sl_mult"]
        atr_tp_mult = risk["atr_tp_mult"]
        min_sl_pct = risk["min_sl_pct"]
        max_sl_pct = risk["max_sl_pct"]
        min_rr = risk["min_rr"]

        lv_target = self._find_targets_using_vp(close, signal_candidate, vp)

        if signal_candidate == "BUY":
            # --- SL CALCULATION ---
            # Start from structural level (Supertrend / VP boundary)
            structural_sl = max(row['supertrend'], val if regime == "TREND" else (val - atr))
            structural_dist = close - structural_sl

            # ATR-based SL (the MINIMUM width)
            atr_sl_dist = atr * atr_sl_mult

            # Use the WIDER of structural or ATR-based
            sl_dist = max(structural_dist, atr_sl_dist)

            # Enforce absolute minimum SL distance (% of price)
            min_abs_dist = close * min_sl_pct
            if sl_dist < min_abs_dist:
                sl_dist = min_abs_dist

            # Enforce maximum SL distance (% of price)
            max_abs_dist = close * max_sl_pct
            if sl_dist > max_abs_dist:
                sl_dist = max_abs_dist

            sl_level = close - sl_dist

            # VP Protection: SL must be OUTSIDE Value Area (below VAL)
            if sl_level > val and regime == "RANGE":
                sl_level = val - (atr * 0.5)
                sl_dist = close - sl_level

            # --- TP CALCULATION ---
            atr_tp_dist = atr * atr_tp_mult

            if lv_target and lv_target > close:
                tp_dist = lv_target - close
                # Ensure LVN target meets minimum R:R
                if tp_dist < sl_dist * min_rr:
                    tp_dist = sl_dist * min_rr
            else:
                tp_dist = max(atr_tp_dist, sl_dist * min_rr)

            tp_level = close + tp_dist

        else:  # SELL
            # --- SL CALCULATION ---
            structural_sl = min(row['supertrend'], vah if regime == "TREND" else (vah + atr))
            structural_dist = structural_sl - close

            atr_sl_dist = atr * atr_sl_mult
            sl_dist = max(structural_dist, atr_sl_dist)

            min_abs_dist = close * min_sl_pct
            if sl_dist < min_abs_dist:
                sl_dist = min_abs_dist

            max_abs_dist = close * max_sl_pct
            if sl_dist > max_abs_dist:
                sl_dist = max_abs_dist

            sl_level = close + sl_dist

            # VP Protection: SL must be OUTSIDE Value Area (above VAH)
            if sl_level < vah and regime == "RANGE":
                sl_level = vah + (atr * 0.5)
                sl_dist = sl_level - close

            # --- TP CALCULATION ---
            atr_tp_dist = atr * atr_tp_mult

            if lv_target and lv_target < close:
                tp_dist = close - lv_target
                if tp_dist < sl_dist * min_rr:
                    tp_dist = sl_dist * min_rr
            else:
                tp_dist = max(atr_tp_dist, sl_dist * min_rr)

            tp_level = close - tp_dist

        # Final R:R verification
        final_rr = tp_dist / sl_dist if sl_dist > 0 else 0
        if final_rr < min_rr:
            tp_dist = sl_dist * min_rr
            if signal_candidate == "BUY":
                tp_level = close + tp_dist
            else:
                tp_level = close - tp_dist
            final_rr = min_rr

        # v3.3: Compute Supertrend-based adaptive trail level
        supertrend_trail = row['supertrend']
        atr_buffer = atr * 0.5  # Half ATR buffer beyond Supertrend
        if signal_candidate == "BUY":
            adaptive_trail_sl = supertrend_trail - atr_buffer
        else:
            adaptive_trail_sl = supertrend_trail + atr_buffer

        return {
            "signal": signal_candidate,
            "confidence": 0.8 + (score/10.0),
            "sl": round(sl_level, 5),
            "tp": round(tp_level, 5),
            "adx": adx,
            "atr": atr,
            "rsi": row.get('rsi', 50),
            "reason": f"{vp_reason} + {score} Confluence [{asset_class} ATR×{atr_sl_mult}]",
            "filters": details,
            "indicators_used": tools,
            "strategy": f"ELITE_VP_{regime}",
            "asset_class": asset_class,
            "sl_distance_pct": round(sl_dist / close * 100, 3),
            "tp_distance_pct": round(tp_dist / close * 100, 3),
            "rr_ratio": round(final_rr, 2),
            "confluence_score": score,
            "regime": regime,
            "supertrend_trail": round(adaptive_trail_sl, 5),
            "volatility_atr_pct": round(atr / close * 100, 3),
            "partial_schedule": self.PARTIAL_SCHEDULE,
            "trail_levels": self.TRAIL_LEVELS,
        }
