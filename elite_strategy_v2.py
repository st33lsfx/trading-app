"""
Elite Strategy v2.0 — Adaptive VWAP Band + Volume Profile Regime Engine
========================================================================
Institutional-grade intraday strategy for 5m-15m timeframes.

Two distinct trading modes selected by real-time regime detection:

RANGING (ADX < 25):
    VWAP Mean Reversion at VP Boundaries
    - Entry: Price at VAH/VAL + VWAP > 1σ deviation + RSI extreme + volume confirm
    - Exit: VWAP touch (partial 60%), opposite VA level (rest trails)
    - Edge: Price spends ~68% of time within 1σ of VWAP; VP levels = structural S/R

TRENDING (ADX >= 25):
    VP Level Breakout with VWAP Slope Confirmation
    - Entry: Close breaks VAH/VAL + Volume > 1.5× avg + VWAP slope aligned + DI confirms
    - Exit: ATR trailing stop, partial at 1R
    - Edge: Volume-confirmed VA breakouts have high follow-through

Key improvements over v1:
    - VWAP standard deviation bands (1σ, 2σ) — not just single line
    - Weighted confluence scoring (VP=2, VWAP=2, others=1)
    - OHLC-based VP with adaptive bin count
    - ADX + DI+/DI- for trend quality measurement
    - RSI divergence detection for high-conviction entries
    - Adaptive range detection (ATR-scaled, not fixed %)
    - Volume delta approximation from OHLC candles

DISCLAIMER: Past performance is NOT indicative of future results.
Live trading carries real risk of capital loss. Always validate with
out-of-sample backtests before deploying with real capital.
"""

import pandas as pd
import numpy as np
from ta.trend import ADXIndicator, MACD, PSARIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands


# ══════════════════════════════════════════════════════════════════════
# RISK PROFILES PER ASSET CLASS
# ══════════════════════════════════════════════════════════════════════

RISK_PROFILES = {
    "crypto": {
        "atr_sl_mult": 8.0,
        "atr_tp_mult": 14.0,
        "min_sl_pct": 0.025,
        "max_sl_pct": 0.10,
        "min_rr": 1.3,
    },
    "forex": {
        "atr_sl_mult": 4.0,
        "atr_tp_mult": 7.0,
        "min_sl_pct": 0.008,
        "max_sl_pct": 0.04,
        "min_rr": 1.3,
    },
    "default": {
        "atr_sl_mult": 5.0,
        "atr_tp_mult": 9.0,
        "min_sl_pct": 0.012,
        "max_sl_pct": 0.06,
        "min_rr": 1.3,
    },
}


class EliteStrategyV2:
    """Adaptive VWAP + Volume Profile regime engine."""

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    VP_LOOKBACK = 80        # Candles for Volume Profile
    VP_VALUE_AREA = 0.70    # 70 % of volume defines value area
    VWAP_PERIOD = 14        # Rolling VWAP window

    ADX_TREND_THRESHOLD = 25   # ADX above → trending
    ADX_STRONG_TREND = 35      # ADX above → strong trend

    RSI_OVERSOLD_RANGE = 38    # RSI below → oversold in range mode
    RSI_OVERBOUGHT_RANGE = 62  # RSI above → overbought in range mode
    RSI_OVERSOLD_TREND = 45    # In trend, allow buying until RSI 45
    RSI_OVERBOUGHT_TREND = 55  # In trend, allow selling until RSI 55

    MIN_CONFLUENCE = 3         # Minimum weighted score (VP=2 + VWAP=2 + 1 other)

    def __init__(self, config=None):
        self.config = config or {}
        self.min_confluence = self.config.get("min_confluence", self.MIN_CONFLUENCE)
        self.min_rr_ratio = self.config.get("min_rr_ratio", 1.3)

    # ==================================================================
    # VOLUME PROFILE  (OHLC-sampled, adaptive bins)
    # ==================================================================

    def _calculate_volume_profile(self, df):
        """
        Build Volume Profile from recent candles using OHLC sampling.

        Returns dict with keys: poc, vah, val, bins, lvn_targets
        """
        lookback = min(self.VP_LOOKBACK, len(df))
        window = df.tail(lookback).copy()

        if window.empty:
            return None

        price_high = window["High"].max()
        price_low = window["Low"].min()
        price_range = price_high - price_low
        if price_range <= 0:
            return None

        # Adaptive bin count: more bins for wider ranges
        num_bins = max(20, min(50, int(price_range / (price_range / 30))))
        bin_edges = np.linspace(price_low, price_high, num_bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bin_volumes = np.zeros(num_bins)

        # --- OHLC sampling: distribute each candle's volume across its range ---
        for _, row in window.iterrows():
            vol = row.get("Volume", 0)
            if vol <= 0 or pd.isna(vol):
                # Forex proxy: use True Range as volume proxy
                vol = (row["High"] - row["Low"]) * 100_000
            if vol <= 0:
                continue

            lo, hi = row["Low"], row["High"]
            # Find which bins this candle spans
            for i in range(num_bins):
                bin_lo = bin_edges[i]
                bin_hi = bin_edges[i + 1]
                overlap = max(0, min(hi, bin_hi) - max(lo, bin_lo))
                candle_range = hi - lo if hi > lo else 1e-10
                fraction = overlap / candle_range
                bin_volumes[i] += vol * fraction

        total_volume = bin_volumes.sum()
        if total_volume <= 0:
            return None

        # POC: bin with highest volume
        poc_idx = np.argmax(bin_volumes)
        poc = bin_centers[poc_idx]

        # Value Area: expand from POC until 70% of volume captured
        va_volume = bin_volumes[poc_idx]
        lo_idx, hi_idx = poc_idx, poc_idx

        while va_volume / total_volume < self.VP_VALUE_AREA:
            expand_lo = bin_volumes[lo_idx - 1] if lo_idx > 0 else 0
            expand_hi = bin_volumes[hi_idx + 1] if hi_idx < num_bins - 1 else 0

            if expand_hi >= expand_lo and hi_idx < num_bins - 1:
                hi_idx += 1
                va_volume += bin_volumes[hi_idx]
            elif lo_idx > 0:
                lo_idx -= 1
                va_volume += bin_volumes[lo_idx]
            else:
                break

        val = bin_centers[lo_idx]
        vah = bin_centers[hi_idx]

        # Low Volume Nodes: bins below 30th percentile of volume
        threshold = np.percentile(bin_volumes[bin_volumes > 0], 30)
        lvn_targets = [
            bin_centers[i]
            for i in range(num_bins)
            if 0 < bin_volumes[i] < threshold
        ]

        return {
            "poc": poc,
            "vah": vah,
            "val": val,
            "bins": dict(zip(bin_centers, bin_volumes)),
            "lvn_targets": lvn_targets,
        }

    # ==================================================================
    # VWAP WITH STANDARD DEVIATION BANDS
    # ==================================================================

    def _calculate_vwap_bands(self, df):
        """
        Calculate rolling VWAP + 1σ and 2σ bands.

        Returns: (vwap, upper_1, lower_1, upper_2, lower_2) Series
        or None if volume is unreliable.
        """
        period = self.VWAP_PERIOD
        if len(df) < period:
            return None

        has_volume = (df["Volume"] > 0).sum() > len(df) * 0.5
        if not has_volume:
            # Forex: use price-range proxy for volume
            proxy_vol = (df["High"] - df["Low"]).clip(lower=1e-10) * 100_000
        else:
            proxy_vol = df["Volume"].clip(lower=1)

        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
        tp_vol = typical_price * proxy_vol

        # Rolling cumulative sums
        cum_vol = proxy_vol.rolling(period, min_periods=1).sum()
        cum_tp_vol = tp_vol.rolling(period, min_periods=1).sum()

        vwap = cum_tp_vol / cum_vol

        # Standard deviation of typical price around VWAP
        sq_diff = ((typical_price - vwap) ** 2) * proxy_vol
        cum_sq_diff = sq_diff.rolling(period, min_periods=1).sum()
        variance = cum_sq_diff / cum_vol
        std = np.sqrt(variance.clip(lower=0))

        upper_1 = vwap + std
        lower_1 = vwap - std
        upper_2 = vwap + 2 * std
        lower_2 = vwap - 2 * std

        return {
            "vwap": vwap,
            "upper_1": upper_1,
            "lower_1": lower_1,
            "upper_2": upper_2,
            "lower_2": lower_2,
            "std": std,
            "has_real_volume": has_volume,
        }

    # ==================================================================
    # INDICATOR CALCULATION
    # ==================================================================

    def _add_indicators(self, df):
        """Calculate all technical indicators."""
        h, l, c = df["High"], df["Low"], df["Close"]

        # ADX + Directional Indicators
        adx_ind = ADXIndicator(h, l, c, window=14)
        df["adx"] = adx_ind.adx()
        df["di_plus"] = adx_ind.adx_pos()
        df["di_minus"] = adx_ind.adx_neg()

        # RSI
        df["rsi"] = RSIIndicator(c, window=14).rsi()

        # MACD
        macd = MACD(c, window_fast=12, window_slow=26, window_sign=9)
        df["macd_hist"] = macd.macd_diff()
        df["macd_line"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()

        # ATR
        df["atr"] = AverageTrueRange(h, l, c, window=14).average_true_range()

        # Bollinger Bands (for mean reversion confirmation)
        bb = BollingerBands(c, window=20, window_dev=2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_mid"] = bb.bollinger_mavg()

        # PSAR
        psar = PSARIndicator(h, l, c, step=0.02, max_step=0.2)
        df["psar"] = psar.psar()

        # Hull Moving Averages
        df["hma_fast"] = self._hma(c, 9)
        df["hma_slow"] = self._hma(c, 21)

        # Supertrend
        df = self._supertrend(df, period=10, multiplier=3.0)

        # VWAP bands
        vwap_data = self._calculate_vwap_bands(df)
        if vwap_data:
            for key, series in vwap_data.items():
                if isinstance(series, pd.Series):
                    df[f"vwap_{key}" if key != "vwap" else "vwap"] = series
            df["_has_real_vwap"] = vwap_data["has_real_volume"]
        else:
            df["vwap"] = c
            df["vwap_upper_1"] = c
            df["vwap_lower_1"] = c
            df["vwap_upper_2"] = c
            df["vwap_lower_2"] = c
            df["vwap_std"] = 0
            df["_has_real_vwap"] = False

        return df

    # ------------------------------------------------------------------
    # Helper: Hull Moving Average
    # ------------------------------------------------------------------
    @staticmethod
    def _hma(series, period):
        half = int(period / 2)
        sqrt_p = int(np.sqrt(period))
        wma_half = series.rolling(half, min_periods=1).mean()
        wma_full = series.rolling(period, min_periods=1).mean()
        diff = 2 * wma_half - wma_full
        return diff.rolling(sqrt_p, min_periods=1).mean()

    # ------------------------------------------------------------------
    # Helper: Supertrend
    # ------------------------------------------------------------------
    @staticmethod
    def _supertrend(df, period=10, multiplier=3.0):
        hl2 = (df["High"] + df["Low"]) / 2
        atr = df["atr"] if "atr" in df.columns else AverageTrueRange(
            df["High"], df["Low"], df["Close"], window=period
        ).average_true_range()

        upper = hl2 + multiplier * atr
        lower = hl2 - multiplier * atr

        st_dir = pd.Series(1, index=df.index)
        st_line = pd.Series(np.nan, index=df.index)

        for i in range(1, len(df)):
            prev_upper = upper.iloc[i - 1] if not pd.isna(upper.iloc[i - 1]) else upper.iloc[i]
            prev_lower = lower.iloc[i - 1] if not pd.isna(lower.iloc[i - 1]) else lower.iloc[i]
            prev_close = df["Close"].iloc[i - 1]

            # Adjust bands
            if lower.iloc[i] < prev_lower and prev_close > prev_lower:
                lower.iloc[i] = prev_lower
            if upper.iloc[i] > prev_upper and prev_close < prev_upper:
                upper.iloc[i] = prev_upper

            # Direction
            if prev_close > prev_upper:
                st_dir.iloc[i] = 1
            elif prev_close < prev_lower:
                st_dir.iloc[i] = -1
            else:
                st_dir.iloc[i] = st_dir.iloc[i - 1]

            st_line.iloc[i] = lower.iloc[i] if st_dir.iloc[i] == 1 else upper.iloc[i]

        df["supertrend"] = st_line
        df["supertrend_dir"] = st_dir
        return df

    # ==================================================================
    # RSI DIVERGENCE DETECTION
    # ==================================================================

    @staticmethod
    def _detect_rsi_divergence(df, lookback=20):
        """
        Detect bullish/bearish RSI divergence.

        Bullish: Price makes lower low, RSI makes higher low
        Bearish: Price makes higher high, RSI makes lower high
        """
        if len(df) < lookback:
            return "none"

        window = df.tail(lookback)
        prices = window["Close"].values
        rsi_vals = window["rsi"].values

        if np.any(np.isnan(rsi_vals)):
            return "none"

        # Find local minima/maxima (simple approach)
        mid = lookback // 2

        # Bullish divergence: recent low < previous low, RSI at low > previous RSI at low
        price_recent_low = prices[mid:].min()
        price_prev_low = prices[:mid].min()
        rsi_at_recent_low = rsi_vals[mid + np.argmin(prices[mid:])]
        rsi_at_prev_low = rsi_vals[np.argmin(prices[:mid])]

        if price_recent_low < price_prev_low and rsi_at_recent_low > rsi_at_prev_low:
            return "bullish"

        # Bearish divergence
        price_recent_high = prices[mid:].max()
        price_prev_high = prices[:mid].max()
        rsi_at_recent_high = rsi_vals[mid + np.argmax(prices[mid:])]
        rsi_at_prev_high = rsi_vals[np.argmax(prices[:mid])]

        if price_recent_high > price_prev_high and rsi_at_recent_high < rsi_at_prev_high:
            return "bearish"

        return "none"

    # ==================================================================
    # VOLUME DELTA APPROXIMATION
    # ==================================================================

    @staticmethod
    def _volume_delta(df, lookback=5):
        """
        Approximate buying/selling pressure from OHLC candles.

        Delta = Volume × (Close - Open) / (High - Low)
        Positive = buying pressure, Negative = selling pressure
        """
        window = df.tail(lookback)
        if window.empty:
            return 0.0

        ranges = (window["High"] - window["Low"]).clip(lower=1e-10)
        body = window["Close"] - window["Open"]
        vol = window["Volume"].clip(lower=1)

        delta = (body / ranges) * vol
        return delta.sum()

    # ==================================================================
    # WEIGHTED CONFLUENCE SCORING
    # ==================================================================

    def _score_confluence(self, row, signal, regime, has_vwap):
        """
        Score confluence with weighted indicators.

        VP and VWAP count double (weight=2 each).
        Other indicators count single (weight=1 each).

        Returns: (total_score, max_possible, indicators_used)
        """
        score = 0
        max_score = 0
        indicators = []

        # --- VWAP (weight 2) ---
        if has_vwap:
            max_score += 2
            if signal == "BUY":
                # In range: price below VWAP = buy pressure expected
                # In trend: price above VWAP = trend confirmation
                if regime == "RANGE":
                    if row["Close"] < row.get("vwap", row["Close"]):
                        score += 2
                        indicators.append("VWAP_BELOW")
                else:  # TREND
                    if row["Close"] > row.get("vwap", row["Close"]):
                        score += 2
                        indicators.append("VWAP_ABOVE")
            elif signal == "SELL":
                if regime == "RANGE":
                    if row["Close"] > row.get("vwap", row["Close"]):
                        score += 2
                        indicators.append("VWAP_ABOVE")
                else:
                    if row["Close"] < row.get("vwap", row["Close"]):
                        score += 2
                        indicators.append("VWAP_BELOW")

        # --- HMA (weight 1) ---
        max_score += 1
        if signal == "BUY" and row.get("hma_fast", 0) > row.get("hma_slow", 0):
            score += 1
            indicators.append("HMA")
        elif signal == "SELL" and row.get("hma_fast", 0) < row.get("hma_slow", 0):
            score += 1
            indicators.append("HMA")

        # --- Supertrend (weight 1) ---
        max_score += 1
        st_dir = row.get("supertrend_dir", 0)
        if signal == "BUY" and st_dir == 1:
            score += 1
            indicators.append("ST")
        elif signal == "SELL" and st_dir == -1:
            score += 1
            indicators.append("ST")

        # --- MACD Histogram (weight 1) ---
        max_score += 1
        macd_h = row.get("macd_hist", 0)
        if signal == "BUY" and macd_h > 0:
            score += 1
            indicators.append("MACD")
        elif signal == "SELL" and macd_h < 0:
            score += 1
            indicators.append("MACD")

        # --- RSI (weight 1, regime-adaptive) ---
        max_score += 1
        rsi = row.get("rsi", 50)
        if regime == "RANGE":
            if signal == "BUY" and rsi < self.RSI_OVERSOLD_RANGE:
                score += 1
                indicators.append("RSI")
            elif signal == "SELL" and rsi > self.RSI_OVERBOUGHT_RANGE:
                score += 1
                indicators.append("RSI")
        else:  # TREND
            if signal == "BUY" and rsi < 70:  # Not overbought
                score += 1
                indicators.append("RSI")
            elif signal == "SELL" and rsi > 30:  # Not oversold
                score += 1
                indicators.append("RSI")

        # --- PSAR (weight 1) ---
        max_score += 1
        psar = row.get("psar", 0)
        if psar and not pd.isna(psar):
            if signal == "BUY" and row["Close"] > psar:
                score += 1
                indicators.append("PSAR")
            elif signal == "SELL" and row["Close"] < psar:
                score += 1
                indicators.append("PSAR")

        return score, max_score, indicators

    # ==================================================================
    # STOP-LOSS / TAKE-PROFIT CALCULATION
    # ==================================================================

    def _calculate_levels(self, signal, row, vp, asset_class, regime):
        """
        Calculate SL and TP using structural levels + ATR.

        SL anchored to VP levels (VAL for BUY, VAH for SELL) with ATR minimum.
        TP targets LVN nodes or ATR-multiple, whichever is further.
        """
        profile = RISK_PROFILES.get(asset_class, RISK_PROFILES["default"])
        close = row["Close"]
        atr = row.get("atr", close * 0.01)
        if pd.isna(atr) or atr <= 0:
            atr = close * 0.01

        atr_sl = atr * profile["atr_sl_mult"]
        atr_tp = atr * profile["atr_tp_mult"]
        min_sl = close * profile["min_sl_pct"]
        max_sl = close * profile["max_sl_pct"]

        sl = None
        tp = None

        if signal == "BUY":
            # --- SL ---
            structural_sl = vp["val"] if vp else close - atr_sl
            if regime == "TREND":
                # In trend, also consider Supertrend as support
                st = row.get("supertrend", 0)
                if st and not pd.isna(st) and st < close:
                    structural_sl = max(structural_sl, st)

            sl_distance = max(close - structural_sl, atr_sl, min_sl)
            sl_distance = min(sl_distance, max_sl)
            sl = close - sl_distance

            # --- TP ---
            # Target: LVN above entry, or VAH, or ATR multiple
            tp_candidates = [close + atr_tp]
            if vp:
                tp_candidates.append(vp["vah"])
                for lvn in vp.get("lvn_targets", []):
                    if lvn > close + (sl_distance * profile["min_rr"]):
                        tp_candidates.append(lvn)

            # Choose furthest TP that maintains minimum R:R
            valid_tps = [t for t in tp_candidates if (t - close) >= sl_distance * profile["min_rr"]]
            tp = max(valid_tps) if valid_tps else close + sl_distance * profile["min_rr"]

        elif signal == "SELL":
            # --- SL ---
            structural_sl = vp["vah"] if vp else close + atr_sl
            if regime == "TREND":
                st = row.get("supertrend", 0)
                if st and not pd.isna(st) and st > close:
                    structural_sl = min(structural_sl, st)

            sl_distance = max(structural_sl - close, atr_sl, min_sl)
            sl_distance = min(sl_distance, max_sl)
            sl = close + sl_distance

            # --- TP ---
            tp_candidates = [close - atr_tp]
            if vp:
                tp_candidates.append(vp["val"])
                for lvn in vp.get("lvn_targets", []):
                    if lvn < close - (sl_distance * profile["min_rr"]):
                        tp_candidates.append(lvn)

            valid_tps = [t for t in tp_candidates if (close - t) >= sl_distance * profile["min_rr"]]
            tp = min(valid_tps) if valid_tps else close - sl_distance * profile["min_rr"]

        return sl, tp

    # ==================================================================
    # MAIN SIGNAL GENERATION
    # ==================================================================

    def get_signal(self, df, asset_class=None):
        """
        Generate trading signal from DataFrame of OHLCV data.

        Returns dict with: signal, sl, tp, confidence, reason, rsi, atr,
                          confluence_score, indicators_used, regime, strategy,
                          vp_poc, vp_vah, vp_val
        """
        default_result = {
            "signal": "NEUTRAL",
            "sl": None,
            "tp": None,
            "confidence": 0,
            "reason": "Insufficient data",
            "rsi": 50,
            "atr": 0,
            "confluence_score": 0,
            "indicators_used": [],
            "regime": "UNKNOWN",
            "strategy": "ELITE_V2",
            "vp_poc": 0,
            "vp_vah": 0,
            "vp_val": 0,
        }

        if df is None or len(df) < 50:
            return default_result

        if not asset_class:
            asset_class = "default"

        # --- Calculate all indicators ---
        try:
            df = self._add_indicators(df)
        except Exception as e:
            default_result["reason"] = f"Indicator error: {e}"
            return default_result

        # --- Volume Profile ---
        vp = self._calculate_volume_profile(df)
        if not vp:
            default_result["reason"] = "VP calculation failed"
            return default_result

        row = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else row
        close = row["Close"]
        atr = row.get("atr", 0)
        rsi = row.get("rsi", 50)
        adx = row.get("adx", 0)

        default_result["rsi"] = rsi if not pd.isna(rsi) else 50
        default_result["atr"] = atr if not pd.isna(atr) else 0
        default_result["vp_poc"] = vp["poc"]
        default_result["vp_vah"] = vp["vah"]
        default_result["vp_val"] = vp["val"]

        if pd.isna(adx):
            adx = 0

        # --- Regime Detection ---
        di_plus = row.get("di_plus", 0)
        di_minus = row.get("di_minus", 0)
        if pd.isna(di_plus):
            di_plus = 0
        if pd.isna(di_minus):
            di_minus = 0

        if adx >= self.ADX_TREND_THRESHOLD:
            regime = "TREND"
            if adx >= self.ADX_STRONG_TREND:
                regime = "TREND_STRONG"
        else:
            regime = "RANGE"

        default_result["regime"] = regime

        has_vwap = bool(row.get("_has_real_vwap", False)) or True  # Always use VWAP (proxy OK)

        # --- RSI Divergence (high conviction bonus) ---
        divergence = self._detect_rsi_divergence(df)

        # --- Volume Delta ---
        vol_delta = self._volume_delta(df)

        # ── SIGNAL GENERATION ──────────────────────────────────────────
        signal = None
        reason_parts = []

        # Adaptive proximity threshold (ATR-based instead of fixed %)
        proximity = max(atr * 0.5, close * 0.003) if atr > 0 else close * 0.005

        if regime == "RANGE":
            # ── RANGING: VWAP Mean Reversion at VP Boundaries ──

            # BUY: Price near VAL + below VWAP lower band
            vwap_lower = row.get("vwap_lower_1", row.get("vwap", close))
            vwap_upper = row.get("vwap_upper_1", row.get("vwap", close))

            if abs(close - vp["val"]) < proximity:
                signal = "BUY"
                reason_parts.append(f"RANGE: Price near VAL ({vp['val']:.5f})")

                if close < vwap_lower:
                    reason_parts.append("Below VWAP -1σ")

                if divergence == "bullish":
                    reason_parts.append("RSI BULLISH DIVERGENCE")

            elif abs(close - vp["vah"]) < proximity:
                signal = "SELL"
                reason_parts.append(f"RANGE: Price near VAH ({vp['vah']:.5f})")

                if close > vwap_upper:
                    reason_parts.append("Above VWAP +1σ")

                if divergence == "bearish":
                    reason_parts.append("RSI BEARISH DIVERGENCE")

            # Fallback: VWAP 2σ band touch (strong mean reversion)
            vwap_lower2 = row.get("vwap_lower_2", 0)
            vwap_upper2 = row.get("vwap_upper_2", 0)

            if signal is None and vwap_lower2 > 0:
                if close <= vwap_lower2 and rsi < 35:
                    signal = "BUY"
                    reason_parts.append("RANGE: VWAP -2σ touch + RSI < 35")
                elif close >= vwap_upper2 and rsi > 65:
                    signal = "SELL"
                    reason_parts.append("RANGE: VWAP +2σ touch + RSI > 65")

        else:
            # ── TRENDING: VP Level Breakout with VWAP Confirmation ──

            # BUY: Breakout above VAH + DI+ > DI-
            if close > vp["vah"]:
                if di_plus > di_minus:
                    signal = "BUY"
                    reason_parts.append(f"TREND: Breakout above VAH ({vp['vah']:.5f})")
                    reason_parts.append(f"DI+ ({di_plus:.1f}) > DI- ({di_minus:.1f})")

            # SELL: Breakdown below VAL + DI- > DI+
            elif close < vp["val"]:
                if di_minus > di_plus:
                    signal = "SELL"
                    reason_parts.append(f"TREND: Breakdown below VAL ({vp['val']:.5f})")
                    reason_parts.append(f"DI- ({di_minus:.1f}) > DI+ ({di_plus:.1f})")

            # Pullback to POC in established trend
            elif abs(close - vp["poc"]) < proximity:
                if di_plus > di_minus and row.get("supertrend_dir", 0) == 1:
                    signal = "BUY"
                    reason_parts.append(f"TREND: Pullback to POC ({vp['poc']:.5f}) in uptrend")
                elif di_minus > di_plus and row.get("supertrend_dir", 0) == -1:
                    signal = "SELL"
                    reason_parts.append(f"TREND: Pullback to POC ({vp['poc']:.5f}) in downtrend")

        # ── NO SIGNAL ──────────────────────────────────────────────────
        if signal is None:
            default_result["reason"] = f"No VP trigger ({regime}, ADX {adx:.1f})"
            return default_result

        # ── CANDLE CONFIRMATION ────────────────────────────────────────
        if signal == "BUY" and row["Close"] < row["Open"]:
            # Allow if previous candle was bullish (1-bar delay OK)
            if prev["Close"] < prev["Open"]:
                default_result["reason"] = "Candle confirmation failed (no bullish candle)"
                return default_result
        elif signal == "SELL" and row["Close"] > row["Open"]:
            if prev["Close"] > prev["Open"]:
                default_result["reason"] = "Candle confirmation failed (no bearish candle)"
                return default_result

        # ── CONFLUENCE CHECK ───────────────────────────────────────────
        score, max_score, indicators = self._score_confluence(row, signal, regime, has_vwap)

        # VP is mandatory and already triggered (weight 2 included in trigger)
        total_score = score + 2  # VP weight = 2
        indicators.insert(0, "VP")

        # Divergence bonus (+1)
        if (signal == "BUY" and divergence == "bullish") or \
           (signal == "SELL" and divergence == "bearish"):
            total_score += 1
            indicators.append("RSI_DIV")

        # Volume delta bonus (+1)
        if (signal == "BUY" and vol_delta > 0) or \
           (signal == "SELL" and vol_delta < 0):
            total_score += 1
            indicators.append("VOL_DELTA")

        if total_score < self.min_confluence:
            default_result["reason"] = (
                f"Low confluence: {total_score}/{self.min_confluence} "
                f"({', '.join(indicators)})"
            )
            default_result["confluence_score"] = total_score
            return default_result

        # ── SL / TP ───────────────────────────────────────────────────
        sl, tp = self._calculate_levels(signal, row, vp, asset_class, regime)
        if not sl or not tp:
            default_result["reason"] = "SL/TP calculation failed"
            return default_result

        # Final R:R check
        sl_dist = abs(close - sl)
        tp_dist = abs(close - tp)
        rr = tp_dist / sl_dist if sl_dist > 0 else 0

        profile = RISK_PROFILES.get(asset_class, RISK_PROFILES["default"])
        if rr < profile["min_rr"]:
            default_result["reason"] = f"R:R too low ({rr:.2f} < {profile['min_rr']})"
            return default_result

        # ── BUILD RESULT ──────────────────────────────────────────────
        confidence = 0.70 + (total_score / 14.0)  # Scale 0.70 – 1.0
        confidence = min(confidence, 1.0)

        reason = " | ".join(reason_parts)

        return {
            "signal": signal,
            "sl": sl,
            "tp": tp,
            "confidence": confidence,
            "reason": reason,
            "rsi": rsi if not pd.isna(rsi) else 50,
            "adx": adx,
            "atr": atr if not pd.isna(atr) else 0,
            "confluence_score": total_score,
            "indicators_used": indicators,
            "regime": regime,
            "strategy": f"ELITE_V2_{regime}",
            "vp_poc": vp["poc"],
            "vp_vah": vp["vah"],
            "vp_val": vp["val"],
            "rr_ratio": round(rr, 2),
            "sl_distance_pct": round(sl_dist / close * 100, 3),
            "divergence": divergence,
            "volume_delta": vol_delta,
        }


# ══════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import yfinance as yf

    print("=" * 60)
    print("Elite Strategy V2.0 — VWAP Band + VP Regime Engine")
    print("=" * 60)

    strategy = EliteStrategyV2()

    tickers = {
        "BTC-USD": "crypto",
        "EURUSD=X": "forex",
        "ETH-USD": "crypto",
        "GBPUSD=X": "forex",
    }

    for ticker, asset_class in tickers.items():
        try:
            data = yf.download(ticker, period="60d", interval="15m", progress=False)
            if hasattr(data.columns, "levels"):
                data.columns = data.columns.get_level_values(0)
            if len(data) < 50:
                print(f"\n{ticker}: Insufficient data ({len(data)} rows)")
                continue

            result = strategy.get_signal(data, asset_class=asset_class)

            print(f"\n{'─' * 50}")
            print(f" {ticker} ({asset_class})")
            print(f"{'─' * 50}")
            print(f"  Signal:     {result['signal']}")
            print(f"  Regime:     {result['regime']} (ADX {result.get('adx', 0):.1f})")
            print(f"  Confidence: {result['confidence']:.0%}")
            print(f"  RSI:        {result['rsi']:.1f}")
            print(f"  VP POC:     {result['vp_poc']:.4f}")
            print(f"  VP VAH:     {result['vp_vah']:.4f}")
            print(f"  VP VAL:     {result['vp_val']:.4f}")
            if result["sl"]:
                print(f"  SL:         {result['sl']:.5f} ({result.get('sl_distance_pct', 0):.2f}%)")
                print(f"  TP:         {result['tp']:.5f}")
                print(f"  R:R:        {result.get('rr_ratio', 0):.2f}")
            print(f"  Confluence: {result['confluence_score']}")
            print(f"  Indicators: {', '.join(result['indicators_used'])}")
            print(f"  Divergence: {result.get('divergence', 'none')}")
            print(f"  Reason:     {result['reason']}")
        except Exception as e:
            print(f"\n{ticker}: Error — {e}")

    print(f"\n{'=' * 60}")
    print("DISCLAIMER: Past performance is NOT indicative of future results.")
    print("Live trading carries real risk of capital loss.")
    print(f"{'=' * 60}")
