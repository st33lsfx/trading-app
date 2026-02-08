"""
Adaptive Volume Profile Strategy (v1.0)
=======================================
Core Logic:
- VWAP (Session/Daily Anchored) + Bands (StdDev)
- Volume Profile (Rolling 24h or Session) -> POC, VAH, VAL
- Adaptive Regime: ADX + VWAP Slope -> Trend vs Range
"""

import pandas as pd
import numpy as np
from ta.trend import ADXIndicator, MACD
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator

class AdaptiveStrategy:
    def __init__(self, config=None):
        self.config = config or {}
        
        # --- Parameters (Default / Optimized) ---
        self.adx_threshold = self.config.get('adx_threshold', 25)
        self.vwap_window = self.config.get('vwap_window', 96) # Approx 24h on 15m
        self.vp_lookback = self.config.get('vp_lookback', 96) 
        self.tp_rr = self.config.get('tp_rr_ratio', 2.0)
        self.sl_atr_mult = self.config.get('sl_atr_mult', 2.0)
        
        # Internal state
        self.regime = "NEUTRAL"

    def _calculate_vwap(self, df):
        """Calculates Rolling VWAP with StdDev Bands."""
        v = df['Volume'].values
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        tp = tp.values
        
        # Rolling VWAP
        vwap = pd.Series(index=df.index, dtype='float64')
        
        # Efficient Rolling Calculation using pandas
        # VWAP = Sum(Price * Vol) / Sum(Vol)
        pv = df['Close'] * df['Volume'] # Use Close or TP
        
        vwap = pv.rolling(window=self.vwap_window, min_periods=1).sum() / \
               df['Volume'].rolling(window=self.vwap_window, min_periods=1).sum()
               
        # Std Bands
        rolling_std = df['Close'].rolling(window=self.vwap_window).std()
        
        return vwap, rolling_std

    def _calculate_vp(self, df):
        """
        Calculates Volume Profile for the last N candles.
        Returns: POC, VAH (70%), VAL (70%)
        """
        subset = df.tail(self.vp_lookback)
        if len(subset) < 10: return None
        
        price_min = subset['Low'].min()
        price_max = subset['High'].max()
        if price_min == price_max: return None
        
        bins = 30 # Resolution
        range_size = price_max - price_min
        bin_size = range_size / bins
        
        vol_profile = {}
        
        # Bucket volumes
        for _, row in subset.iterrows():
            close_px = row['Close']
            vol = row['Volume']
            bin_idx = int((close_px - price_min) / bin_size)
            # Clamp bin_idx to verify it's within range 0..29
            bin_idx = min(max(bin_idx, 0), bins - 1)
            vol_profile[bin_idx] = vol_profile.get(bin_idx, 0) + vol
            
        # Find POC
        if not vol_profile: return None
        poc_bin = max(vol_profile, key=vol_profile.get)
        poc_price = price_min + (poc_bin + 0.5) * bin_size
        
        # Value Area
        total_vol = sum(vol_profile.values())
        sorted_bins = sorted(vol_profile.items(), key=lambda item: item[1], reverse=True)
        
        va_vol = 0
        va_bins = []
        for b, v in sorted_bins:
            va_vol += v
            va_bins.append(b)
            if va_vol >= total_vol * 0.70:
                break
                
        if not va_bins: return None
        
        vah_price = price_min + (max(va_bins) + 1) * bin_size
        val_price = price_min + min(va_bins) * bin_size
        
        return {
            "POC": poc_price,
            "VAH": vah_price,
            "VAL": val_price,
            "TotalVol": total_vol
        }

    def add_indicators(self, df):
        """Adds all necessary indicators to the DataFrame."""
        df = df.copy()
        
        # 1. ADX (Trend Strength)
        adx_ind = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
        df['ADX'] = adx_ind.adx()
        
        # 2. ATR (Volatility)
        df['ATR'] = AverageTrueRange(df['High'], df['Low'], df['Close'], window=14).average_true_range()
        
        # 3. RSI (Momentum)
        df['RSI'] = RSIIndicator(df['Close'], window=14).rsi()
        
        # 4. VWAP
        df['VWAP'], df['VWAP_STD'] = self._calculate_vwap(df)
        df['VWAP_Upper'] = df['VWAP'] + (2.0 * df['VWAP_STD'])
        df['VWAP_Lower'] = df['VWAP'] - (2.0 * df['VWAP_STD'])
        
        return df

    def get_signal(self, df):
        """
        Main Signal Logic. 
        Returns dict with keys: 'signal', 'sl', 'tp', 'reason', 'regime'
        """
        # Ensure minimal history
        if len(df) < self.vwap_window:
            return {'signal': 'NEUTRAL', 'reason': 'Not enough data'}
            
        # Add indicators if missing
        if 'ADX' not in df.columns:
            df = self.add_indicators(df)
            
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. Determine Regime
        is_trending = curr['ADX'] > self.adx_threshold
        # Check VWAP Slope (comparing current vs 5 bars ago)
        vwap_slope_up = curr['VWAP'] > df.iloc[-5]['VWAP']
        
        self.regime = "TREND" if is_trending else "RANGE"
        
        # 2. Get Volume Profile Levels
        vp = self._calculate_vp(df)
        if not vp:
            return {'signal': 'NEUTRAL', 'reason': 'No VP data'}
            
        poc = vp['POC']
        vah = vp['VAH']
        val = vp['VAL']
        close_px = curr['Close']
        
        signal = "NEUTRAL"
        reason = ""
        
        # --- LOGIC ---
        
        if self.regime == "TREND":
            # TREND LONG
            # Case A: Breakout above VAH + VWAP Slope Up
            if close_px > vah and vwap_slope_up and curr['Close'] > curr['VWAP']:
                # Pullback confirmation or direct breakout?
                # Let's require a small momentum confirmation (RSI > 50)
                if curr['RSI'] > 50:
                    signal = "BUY"
                    reason = "Trend Breakout > VAH"
            
            # Case B: Pullback to VWAP in Uptrend
            elif abs(close_px - curr['VWAP']) < (curr['ATR'] * 0.5) and vwap_slope_up:
                if curr['Close'] > curr['Open']: # Bounce candle
                    signal = "BUY"
                    reason = "Trend Pullback to VWAP"
            
            # TREND SHORT
            # Case A: Breakdown below VAL + VWAP Slope Down
            elif close_px < val and not vwap_slope_up and curr['Close'] < curr['VWAP']:
                if curr['RSI'] < 50:
                    signal = "SELL"
                    reason = "Trend Breakdown < VAL"

        elif self.regime == "RANGE":
            # Mean Reversion Logic
            # LONG at VAL (Support)
            if close_px <= val and close_px > (val - curr['ATR']):
                # Rejection candle helps
                if curr['Close'] > curr['Open']: 
                    signal = "BUY"
                    reason = "Range Reversal @ VAL"
            
            # SHORT at VAH (Resistance)
            elif close_px >= vah and close_px < (vah + curr['ATR']):
                if curr['Close'] < curr['Open']:
                    signal = "SELL"
                    reason = "Range Reversal @ VAH"
                    
        # --- RISK MANAGEMENT ---
        sl_price = 0.0
        tp_price = 0.0
        
        if signal == "BUY":
            # SL below recent swing low or ATR based
            sl_dist = curr['ATR'] * self.sl_atr_mult
            sl_price = close_px - sl_dist
            # TP based on RR or Structure?
            # Range: Target POC or VAH. Trend: ATR multiple
            if self.regime == "RANGE":
                tp_price = poc # Conservative
                if tp_price <= close_px: tp_price = vah # Extend to VAH
            else:
                tp_price = close_px + (sl_dist * self.tp_rr)
                
        elif signal == "SELL":
            sl_dist = curr['ATR'] * self.sl_atr_mult
            sl_price = close_px + sl_dist
            if self.regime == "RANGE":
                tp_price = poc
                if tp_price >= close_px: tp_price = val
            else:
                tp_price = close_px - (sl_dist * self.tp_rr)
                
        return {
            'signal': signal,
            'sl': sl_price,
            'tp': tp_price,
            'reason': f"[{self.regime}] {reason}",
            'regime': self.regime,
            'vp_levels': vp,
            'adx': curr['ADX']
        }
