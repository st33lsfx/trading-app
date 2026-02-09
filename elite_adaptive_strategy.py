"""
Elite Adaptive Strategy (v3.0)
==============================
A high-performance trading logic combining:
1. Composite Volume Profile (Rolling Multi-Day) -> Stronger S/R
2. Adaptive Regime Detection (Trend/Range/Noise)
3. Volatility-Adjusted Risk Management
4. Institutional Order Flow Proxies (VWAP + CVD approximation)

Designed for robust profitability in Crypto & Forex markets.
"""

import pandas as pd
import numpy as np
from ta.trend import ADXIndicator, EMAIndicator, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.momentum import RSIIndicator

class EliteAdaptiveStrategy:
    def __init__(self, config=None):
        self.config = config or {}
        
        # --- Core Parameters ---
        # Regime
        self.adx_threshold = self.config.get('adx_threshold', 25)
        self.adx_len = self.config.get('adx_len', 14)
        
        # Volume Profile
        self.vp_lookback_bars = self.config.get('vp_lookback', 288) # ~3 days of 15m (96*3)
        self.vp_bins = self.config.get('vp_bins', 50)
        self.vp_va_pct = self.config.get('vp_va_pct', 0.70)
        
        # VWAP
        self.vwap_window = self.config.get('vwap_window', 96) # ~1 day
        self.vwap_mult = self.config.get('vwap_mult', 2.0)
        
        # Filter & Execution
        self.rsi_period = self.config.get('rsi_period', 14)
        self.tp_rr = self.config.get('tp_rr', 2.0)
        # Fix: Support both keys due to bot.py config mismatch
        self.sl_atr = self.config.get('sl_atr', self.config.get('atr_sl_mult', 2.0))
        
        # State
        self.last_vp = None
        self.last_regime = "NEUTRAL"

    def _calculate_vwap(self, df):
        """Calculates Rolling VWAP with Standard Deviation Bands."""
        # Typical Price
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        # Volume-weighted Price
        pv = tp * df['Volume']
        
        # Rolling sums for VWAP
        cum_pv = pv.rolling(window=self.vwap_window, min_periods=1).sum()
        cum_vol = df['Volume'].rolling(window=self.vwap_window, min_periods=1).sum()
        
        vwap = cum_pv / cum_vol
        
        # Rolling Std Dev for Bands (using close price deviation from VWAP)
        # Standard approach: StdDev of Close over the window
        # Better approach: Variance of Price relative to VWAP? Keep it simple: Rolling STD of Close.
        rolling_std = df['Close'].rolling(window=self.vwap_window).std()
        
        return vwap, rolling_std

    def _calculate_composite_vp(self, df):
        """
        Calculates a Composite Volume Profile over `vp_lookback_bars`.
        Returns dictionary with POC, VAH, VAL, and distribution density.
        """
        if len(df) < self.vp_lookback_bars:
            return None
            
        # Slice the data
        subset = df.iloc[-self.vp_lookback_bars:]
        
        price_min = subset['Low'].min()
        price_max = subset['High'].max()
        
        if price_min == price_max: return None
        
        # Create Histogram
        range_size = price_max - price_min
        bin_size = range_size / self.vp_bins
        
        # We need to distribute volume into bins
        # Vectorized approach is faster than iterating rows
        # But for clarity/robustness with pandas, we iterate or use cut
        
        # Using pandas cut
        # We assign each row's volume to a price bin based on Close (approximation)
        # More accurate: distribute Volume across (High-Low), but Close is standard for fast VP.
        
        bins = np.linspace(price_min, price_max, self.vp_bins + 1)
        # Labels are the mid-points
        bin_mids = (bins[:-1] + bins[1:]) / 2
        
        # Assign bins
        try:
            # pd.cut returns categories. We want to sum volume per category.
            binned = pd.cut(subset['Close'], bins=bins, labels=bin_mids, include_lowest=True)
            vp_series = subset['Volume'].groupby(binned, observed=False).sum()
        except Exception:
            # Fallback (rare float errors)
            return None
            
        # Find POC (Point of Control)
        if vp_series.empty: return None
        
        poc_price = vp_series.idxmax() # The bin midpoint with max volume
        
        # Calculate Value Area (70%)
        total_vol = vp_series.sum()
        sorted_bins = vp_series.sort_values(ascending=False)
        
        cum_vol = 0
        va_bins = []
        for price, vol in sorted_bins.items():
            cum_vol += vol
            va_bins.append(price)
            if cum_vol >= total_vol * self.vp_va_pct:
                break
                
        # VAH / VAL (Highest and Lowest price in the VA bins)
        vah = max(va_bins)
        val = min(va_bins)
        
        return {
            "POC": float(poc_price),
            "VAH": float(vah),
            "VAL": float(val),
            "Profile": vp_series
        }

    def add_indicators(self, df):
        """Adds technical indicators to the dataframe."""
        df = df.copy()
        
        # 1. Trend Strength (ADX)
        adx_ind = ADXIndicator(df['High'], df['Low'], df['Close'], window=self.adx_len)
        df['ADX'] = adx_ind.adx()
        df['DIP'] = adx_ind.adx_pos()
        df['DIM'] = adx_ind.adx_neg()
        
        # 2. Volatility (ATR)
        df['ATR'] = AverageTrueRange(df['High'], df['Low'], df['Close'], window=14).average_true_range()
        
        # 3. Momentum (RSI)
        df['RSI'] = RSIIndicator(df['Close'], window=self.rsi_period).rsi()
        
        # 4. Volume Moving Average (for Relative Volume)
        df['VolMA'] = df['Volume'].rolling(window=20).mean()
        df['RVol'] = df['Volume'] / df['VolMA'] # Relative Volume
        
        # 5. VWAP & Bands
        df['VWAP'], df['VWAP_Std'] = self._calculate_vwap(df)
        df['VWAP_Upper'] = df['VWAP'] + (self.vwap_mult * df['VWAP_Std'])
        df['VWAP_Lower'] = df['VWAP'] - (self.vwap_mult * df['VWAP_Std'])
        
        # 6. EMA Trend Filter
        df['EMA_200'] = EMAIndicator(df['Close'], window=200).ema_indicator()
        
        return df

    def get_signal(self, df):
        """
        Generates a trading signal for the last candle.
        Returns: { 'signal': 'BUY'|'SELL'|'NEUTRAL', 'sl': float, 'tp': float, 'reason': str }
        """
        # Ensure we have enough data (min lookback)
        if len(df) < max(self.vp_lookback_bars, 200):
            return {'signal': 'NEUTRAL', 'reason': 'Insufficient Data'}
            
        # Calc Indicators if missing
        if 'ADX' not in df.columns:
            df = self.add_indicators(df)
            
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- 1. REGIME IDENTIFICATION ---
        # Trend: ADX > Threshold
        # Range: Strictly ADX < 18 (avoid falling knives in weak trends)
        
        is_trend = curr['ADX'] > self.adx_threshold
        is_range = curr['ADX'] < 18 # Stricter Range Definition
        self.last_regime = "TREND" if is_trend else ("RANGE" if is_range else "NEUTRAL")
        
        # --- 2. VOLUME PROFILE LEVELS ---
        # We calculate VP on the window ending at previous candle (closed data)
        # to avoid repainting.
        vp = self._calculate_composite_vp(df.iloc[:-1]) 
        if not vp:
             return {'signal': 'NEUTRAL', 'reason': 'VP Calc Failed'}
             
        poc = vp['POC']
        vah = vp['VAH']
        val = vp['VAL']
        
        signal = "NEUTRAL"
        reason = "No Setup" # Default reason
        setup_type = "" # 'Breakout', 'Pullback', 'MeanReversion'
        
        # Helper: Relative Volume check (Volume > MA)
        vol_confirmed = curr['RVol'] > 1.0
        
        # Helper: Bullish/Bearish Candle
        is_bullish = curr['Close'] > curr['Open']
        is_bearish = curr['Close'] < curr['Open']
        
        # Helper: DI Direction Confirmation
        di_bullish = curr['DIP'] > curr['DIM']
        di_bearish = curr['DIM'] > curr['DIP']

        # Helper: Bullish/Bearish Candle
        is_bullish = curr['Close'] > curr['Open']
        is_bearish = curr['Close'] < curr['Open']
        
        # Helper: DI Direction Confirmation
        di_bullish = curr['DIP'] > curr['DIM']
        di_bearish = curr['DIM'] > curr['DIP']

        confidence = 0.55 # Base confidence (MIN_CONFIDENCE limit)
        
        # Boost Confidence with Confluence
        if vol_confirmed: confidence += 0.1
        if curr['ADX'] > 30 and is_trend: confidence += 0.1
        if 40 < curr['RSI'] < 60: confidence += 0.05 # Safe RSI zone
        if setup_type in ['Trend_Breakout', 'Trend_Pullback']: confidence += 0.1 # Trend > Range reliability

        # --- LOGIC: TREND REGIME ---
        if is_trend:
            # ---------------------------------------------------------
            # LONG TREND SETUP
            # 1. Price above EMA200 (Long-term trend)
            # 2. Price > VWAP (Mid-term trend)
            # A) Breakout above VAH
            # B) Pullback to VWAP or POC
            # ---------------------------------------------------------
            if curr['Close'] > curr['EMA_200'] and curr['Close'] > curr['VWAP'] and di_bullish:
                
                # A) VAH Breakout
                # Check if we crossed above VAH recently and held
                if prev['Close'] < vah and curr['Close'] > vah and vol_confirmed:
                    if curr['RSI'] > 50 and curr['RSI'] < 70: # Momentum OK, not overbought
                        signal = "BUY"
                        reason = f"Trend Breakout > VAH ({vah:.2f})"
                        setup_type = "Trend_Breakout"
                        
                # B) VWAP Pullback
                # Check near VWAP + Bullish rejection
                elif abs(curr['Low'] - curr['VWAP']) < (curr['ATR'] * 0.5):
                    if is_bullish and curr['RSI'] > 40: # Bounce req
                         signal = "BUY"
                         reason = "Trend Pullback to VWAP"
                         setup_type = "Trend_Pullback"

            # ---------------------------------------------------------
            # SHORT TREND SETUP
            # 1. Price below EMA200
            # 2. Price < VWAP
            # ---------------------------------------------------------
            elif curr['Close'] < curr['EMA_200'] and curr['Close'] < curr['VWAP'] and di_bearish:
                
                # A) VAL Breakdown
                if prev['Close'] > val and curr['Close'] < val and vol_confirmed:
                    if curr['RSI'] < 50 and curr['RSI'] > 30:
                        signal = "SELL"
                        reason = f"Trend Breakdown < VAL ({val:.2f})"
                        setup_type = "Trend_Breakout"
                        
                # B) VWAP Pullback (Short)
                elif abs(curr['High'] - curr['VWAP']) < (curr['ATR'] * 0.5):
                    if is_bearish and curr['RSI'] < 60:
                        signal = "SELL"
                        reason = "Trend Pullback to VWAP (Short)"
                        setup_type = "Trend_Pullback"

        # --- LOGIC: RANGE REGIME ---
        elif is_range: # Strictly RANGE (ADX < 18)
            # ---------------------------------------------------------
            # MEAN REVERSION (Range Trading)
            # Buy at VAL / VWAP Lower Band
            # Sell at VAH / VWAP Upper Band
            # Context: RSI Extremes useful here
            # ---------------------------------------------------------
            
            # LONG: Price @ VAL or VWAP Lower
            near_val = abs(curr['Low'] - val) < (curr['ATR'] * 0.5)
            below_vwap_lower = curr['Low'] < curr['VWAP_Lower']
            
            if (near_val or below_vwap_lower) and is_bullish:
                if curr['RSI'] < 40 and di_bullish: # Oversold + DI+ starting to take over?
                    signal = "BUY"
                    reason = "Range Reversal (VAL/Band Support)"
                    setup_type = "Mean_Reversion"
            
            # SHORT: Price @ VAH or VWAP Upper
            near_vah = abs(curr['High'] - vah) < (curr['ATR'] * 0.5)
            above_vwap_upper = curr['High'] > curr['VWAP_Upper']
            
            if (near_vah or above_vwap_upper) and is_bearish:
                if curr['RSI'] > 60 and di_bearish: # Overbought + DI- starting to take over?
                    signal = "SELL"
                    reason = "Range Reversal (VAH/Band Resistance)"
                    setup_type = "Mean_Reversion"

        # --- RISK MANAGEMENT (SL/TP) ---
        if signal == "NEUTRAL":
            return {
                'signal': 'NEUTRAL', 
                'reason': reason,
                'rsi': float(curr['RSI']),
                'adx': float(curr['ADX']),
                'regime': self.last_regime
            }
            
        sl_price = 0.0
        tp_price = 0.0
        atr = curr['ATR']
        close = curr['Close']
        
        # Adaptive Multipliers
        # Trend setups: Wider SL, Higher TP
        # Range setups: Tight SL, Target Middle
        
        if setup_type in ["Trend_Breakout", "Trend_Pullback"]:
            used_sl_mult = self.sl_atr * 1.5 # Looser SL for trending
            used_tp_rr = self.tp_rr # Target 2:1 or 3:1
        else: # Mean Reversion
            used_sl_mult = self.sl_atr # Tighter SL
            used_tp_rr = 1.5 # Smaller target (revert to mean)
            
        if signal == "BUY":
            sl_price = close - (atr * used_sl_mult)
            # Ensure SL is below support (e.g. below VAL or VWAP if close)
            # If Pullback, SL below swing low (approximated by Low - ATR)
            if setup_type == "Trend_Pullback":
                sl_price = min(sl_price, curr['Low'] - atr)
                
            tp_dist = (close - sl_price) * used_tp_rr
            tp_price = close + tp_dist
            
        elif signal == "SELL":
            sl_price = close + (atr * used_sl_mult)
            if setup_type == "Trend_Pullback":
                sl_price = max(sl_price, curr['High'] + atr)
                
            tp_dist = (sl_price - close) * used_tp_rr
            tp_price = close - tp_dist
            
        return {
            'signal': signal,
            'sl': float(sl_price),
            'tp': float(tp_price),
            'reason': reason,
            'setup': setup_type,
            'regime': self.last_regime,
            'confidence': confidence,
            'rsi': float(curr['RSI']),
            'adx': float(curr['ADX']),
            'vp': vp
        }
