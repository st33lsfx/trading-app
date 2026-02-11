"""
Elite Adaptive Strategy (v3.1) — Session VP, VWAP, Smart Money Concept, Big Trades
===================================================================================
- Session Volume Profile: POC, VAH, VAL (správné zóny)
- VWAP: Premium (nad VWAP) = prodejní zóna, Discount (pod VWAP) = nákupní zóna
- Smart Money Concept: swing high/low (struktura), vstup jen u S/R
- Big Trades: vstup jen při zvýšeném objemu (min. relativní volume)
"""

import pandas as pd
import numpy as np
from ta.trend import ADXIndicator, EMAIndicator, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.momentum import RSIIndicator

class EliteAdaptiveStrategy:
    def __init__(self, config=None):
        self.config = config or {}
        
        self.adx_threshold = self.config.get('adx_threshold', 25)
        self.adx_len = self.config.get('adx_len', 14)
        
        self.use_session_vp = self.config.get('use_session_vp', True)
        self.session_start_hour = self.config.get('session_start_hour', 0)
        self.session_start_minute = self.config.get('session_start_minute', 0)
        self.vp_lookback_bars = self.config.get('vp_lookback', 288)
        self.vp_bins = self.config.get('vp_bins', 50)
        self.vp_va_pct = self.config.get('vp_va_pct', 0.70)
        self.min_session_bars_for_vp = self.config.get('min_session_bars_for_vp', 5)
        
        self.vwap_window = self.config.get('vwap_window', 96)
        self.vwap_mult = self.config.get('vwap_mult', 2.0)
        
        self.rsi_period = self.config.get('rsi_period', 14)
        self.tp_rr = self.config.get('tp_rr', 2.0)
        self.sl_atr = self.config.get('sl_atr', self.config.get('atr_sl_mult', 2.0))
        
        # Big Trades: crypto vyžaduje RVol >= 0.9 (blízko průměru); příliš vysoké = 0 obchodů
        self.min_rvol = self.config.get('min_rvol_big_trade', 0.9)
        # SMC: swing high/low - default OFF (neprověřené, blokuje příliš mnoho setupů)
        self.pivot_len = self.config.get('pivot_len', 5)
        self.use_smc = self.config.get('use_smc_structure', False)
        # Forex: jen mean reversion u VAL/VAH (trend breakouts na forexu často selhávají)
        self.forex_range_only = self.config.get('forex_range_only', False)
        # Forex mode: používat jen VWAP/EMA/RSI (ne VP - syntetický volume)
        self.forex_mode = self.config.get('forex_mode', False)
        
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

    def _get_swing_highs_lows(self, df, lookback=30):
        """
        SMC: detekce swing high / swing low (pivot) za posledních lookback barů.
        Vrací (last_swing_high_price, last_swing_low_price) nebo (None, None).
        """
        if len(df) < self.pivot_len * 2 + 1 or lookback <= 0:
            return None, None
        subset = df.iloc[-lookback:]
        h = subset["High"].values
        l = subset["Low"].values
        n = len(h)
        k = self.pivot_len
        last_sh = None
        last_sl = None
        for i in range(k, n - k):
            if h[i] == np.max(h[i - k : i + k + 1]):
                last_sh = h[i]
            if l[i] == np.min(l[i - k : i + k + 1]):
                last_sl = l[i]
        return last_sh, last_sl

    def _calculate_session_vp(self, df):
        """
        Session Volume Profile: only from start of current session (e.g. today 00:00 UTC).
        Returns POC, VAH, VAL (70% value area). Used for intraday S/R.
        """
        if df.empty or not hasattr(df.index, 'date'):
            return None
        current_time = df.index[-1]
        try:
            current_day = current_time.date() if hasattr(current_time, 'date') else current_time
        except Exception:
            return None
        subset = df[df.index.date == current_day].copy()
        if len(subset) < self.min_session_bars_for_vp:
            return None
        # Forex often has Volume=0; use range as proxy
        vol = subset['Volume'].replace(0, np.nan).fillna((subset['High'] - subset['Low']) * 100_000)
        subset = subset.assign(_vol=vol)
        price_min = subset['Low'].min()
        price_max = subset['High'].max()
        if price_min >= price_max:
            return None
        bins_edges = np.linspace(price_min, price_max, self.vp_bins + 1)
        bin_mids = (bins_edges[:-1] + bins_edges[1:]) / 2
        try:
            binned = pd.cut(subset['Close'], bins=bins_edges, labels=bin_mids, include_lowest=True)
            vp_series = subset['_vol'].groupby(binned, observed=False).sum()
        except Exception:
            return None
        if vp_series.empty:
            return None
        poc_price = float(vp_series.idxmax())
        total_vol = vp_series.sum()
        sorted_bins = vp_series.sort_values(ascending=False)
        cum_vol = 0
        va_bins = []
        for price, vol in sorted_bins.items():
            cum_vol += vol
            va_bins.append(float(price))
            if cum_vol >= total_vol * self.vp_va_pct:
                break
        vah = max(va_bins)
        val = min(va_bins)
        return {
            "POC": poc_price,
            "VAH": vah,
            "VAL": val,
            "Profile": vp_series,
            "source": "session",
        }

    def _calculate_composite_vp(self, df):
        """
        Calculates a Composite Volume Profile over `vp_lookback_bars`.
        Returns dictionary with POC, VAH, VAL, and distribution density.
        """
        if len(df) < self.vp_lookback_bars:
            return None
            
        subset = df.iloc[-self.vp_lookback_bars:].copy()
        price_min = subset['Low'].min()
        price_max = subset['High'].max()
        if price_min == price_max:
            return None
        # Forex: Volume often 0 -> use (High-Low) as proxy
        vol = subset['Volume'].replace(0, np.nan).fillna((subset['High'] - subset['Low']) * 100_000)
        subset = subset.assign(_vol=vol)
        bins = np.linspace(price_min, price_max, self.vp_bins + 1)
        bin_mids = (bins[:-1] + bins[1:]) / 2
        try:
            binned = pd.cut(subset['Close'], bins=bins, labels=bin_mids, include_lowest=True)
            vp_series = subset['_vol'].groupby(binned, observed=False).sum()
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
            "Profile": vp_series,
            "source": "composite",
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
        df['EMA_20'] = EMAIndicator(df['Close'], window=20).ema_indicator()
        
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
        # TREND = ADX >= threshold; RANGE = ADX < threshold (no gap -> more signals)
        is_trend = curr['ADX'] >= self.adx_threshold
        is_range = not is_trend
        self.last_regime = "TREND" if is_trend else "RANGE"
        
        # --- 2. VOLUME PROFILE LEVELS (Session VP preferred, then composite) ---
        # FOREX MODE: Skip VP (syntetický volume), používat jen VWAP bands
        vp = None
        poc = vah = val = None
        
        if not self.forex_mode:
            # Crypto: Session VP = today's session only -> correct VAH/VAL/POC for intraday
            if self.use_session_vp:
                vp = self._calculate_session_vp(df.iloc[:-1])
            if vp is None and len(df) >= self.vp_lookback_bars:
                vp = self._calculate_composite_vp(df.iloc[:-1])
            if vp is None:
                return {'signal': 'NEUTRAL', 'reason': 'VP Calc Failed (session + composite)'}
            poc = vp['POC']
            vah = vp['VAH']
            val = vp['VAL']
        else:
            # Forex: používáme VWAP bands jako S/R
            vp = {'source': 'forex_vwap_only'}
        
        signal = "NEUTRAL"
        reason = "No Setup"
        setup_type = ""

        # --- Volume Filter ---
        # Crypto: Volume je skutečný → povolíme všechny setupy (vol_confirmed = True vždy)
        # Forex: Volume je syntetický → používáme RVol filter
        # DEBUG: v5.2 update - crypto volume filter vypnut
        if self.forex_mode:
            # Forex: vyžadujeme min. RVol
            vol_confirmed = curr.get("RVol", 0) >= 0.5 or pd.isna(curr.get("RVol"))
        else:
            # Crypto: volume filter OFF (skutečný volume, všechny setupy OK)
            vol_confirmed = True  # v5.2: Always True for crypto
        vwap = curr["VWAP"]
        close_px = curr["Close"]

        # --- VWAP Premium / Discount (Smart Money) ---
        in_discount = close_px < vwap  # pod VWAP = nákupní zóna
        in_premium = close_px > vwap   # nad VWAP = prodejní zóna

        is_bullish = curr["Close"] > curr["Open"]
        is_bearish = curr["Close"] < curr["Open"]
        di_bullish = curr["DIP"] > curr["DIM"]
        di_bearish = curr["DIM"] > curr["DIP"]
        atr_half = curr["ATR"] * 0.5

        # SMC: poslední swing high/low (pro strukturu)
        last_sh, last_sl = self._get_swing_highs_lows(df.iloc[:-1], lookback=25) if self.use_smc else (None, None)
        atr_ = curr["ATR"]
        near_swing_low = (last_sl is not None and abs(curr["Low"] - last_sl) <= atr_) if last_sl is not None else True
        near_swing_high = (last_sh is not None and abs(curr["High"] - last_sh) <= atr_) if last_sh is not None else True

        confidence = 0.55
        if vol_confirmed:
            confidence += 0.1
        if curr["ADX"] > 30 and is_trend:
            confidence += 0.1

        # ========== FOREX MODE: Simple VWAP + EMA Strategy (no VP) ==========
        if self.forex_mode:
            # Forex: Zjednodušená strategie - jen VWAP + RSI (bez EMA filtru)
            # Důvod: EMA 200 na 15m je moc pomalé, RSI + VWAP stačí
            
            # TREND režim: Trend following s VWAP jako S/R
            if is_trend:
                # LONG: price nad VWAP (bullish bias), pullback, RSI ne extrémní
                if curr["Close"] > vwap and curr["RSI"] < 60 and vol_confirmed:
                    # Pullback k VWAP nebo EMA20
                    if abs(curr["Low"] - vwap) < atr_ or abs(curr["Low"] - curr["EMA_20"]) < atr_half:
                        if is_bullish and di_bullish:
                            signal = "BUY"
                            reason = "Forex: Trend Pullback (Long)"
                            setup_type = "Trend_Pullback"
                            confidence += 0.05
                
                # SHORT: price pod VWAP (bearish bias), pullback, RSI ne extrémní
                elif curr["Close"] < vwap and curr["RSI"] > 40 and vol_confirmed:
                    if abs(curr["High"] - vwap) < atr_ or abs(curr["High"] - curr["EMA_20"]) < atr_half:
                        if is_bearish and di_bearish:
                            signal = "SELL"
                            reason = "Forex: Trend Pullback (Short)"
                            setup_type = "Trend_Pullback"
                            confidence += 0.05
            
            # RANGE režim: Mean reversion u VWAP bands (discount/premium)
            elif is_range and curr["ADX"] >= 12:
                # LONG: bounce z VWAP lower (discount zóna)
                at_lower = curr["Low"] <= curr["VWAP_Lower"] or (curr["Close"] - curr["VWAP_Lower"]) < atr_ * 0.5
                if at_lower and curr["RSI"] < 50 and vol_confirmed:
                    if is_bullish or curr["Close"] > curr["Open"]:
                        signal = "BUY"
                        reason = "Forex: VWAP Lower Bounce"
                        setup_type = "Mean_Reversion"
                
                # SHORT: rejection z VWAP upper (premium zóna)
                at_upper = curr["High"] >= curr["VWAP_Upper"] or (curr["VWAP_Upper"] - curr["Close"]) < atr_ * 0.5
                if signal == "NEUTRAL" and at_upper and curr["RSI"] > 50 and vol_confirmed:
                    if is_bearish or curr["Close"] < curr["Open"]:
                        signal = "SELL"
                        reason = "Forex: VWAP Upper Rejection"
                        setup_type = "Mean_Reversion"
        
        # ========== CRYPTO MODE: VP Strategy (original) ==========
        # --- TREND: breakouts s volume, pullback k VWAP v trendu ---
        # forex_range_only: skip trend – obchodujeme jen VAL/VAH mean reversion
        elif is_trend and not self.forex_range_only:
            if curr["Close"] > curr["EMA_200"] and curr["Close"] > vwap and di_bullish:
                if prev["Close"] < vah and curr["Close"] > vah and vol_confirmed and 50 < curr["RSI"] < 70:
                    signal = "BUY"
                    reason = f"Trend Breakout > VAH ({vah:.2f})"
                    setup_type = "Trend_Breakout"
                elif abs(curr["Low"] - vwap) < atr_half and is_bullish and curr["RSI"] > 40 and vol_confirmed:
                    signal = "BUY"
                    reason = "Trend Pullback to VWAP"
                    setup_type = "Trend_Pullback"

            elif curr["Close"] < curr["EMA_200"] and curr["Close"] < vwap and di_bearish:
                if prev["Close"] > val and curr["Close"] < val and vol_confirmed and 30 < curr["RSI"] < 50:
                    signal = "SELL"
                    reason = f"Trend Breakdown < VAL ({val:.2f})"
                    setup_type = "Trend_Breakout"
                elif abs(curr["High"] - vwap) < atr_half and is_bearish and curr["RSI"] < 60 and vol_confirmed:
                    signal = "SELL"
                    reason = "Trend Pullback to VWAP (Short)"
                    setup_type = "Trend_Pullback"

        # --- RANGE: vstup u VAL/VAH, v zóně hodnoty. Vyhýbáme se velmi slabému ADX (choppy). ---
        elif is_range and vol_confirmed and curr["ADX"] >= 12:
            # Zpřísněné podmínky: close musí být v zóně, ne moc daleko od VAL/VAH
            # BUY: close mezi VAL-0.5ATR a VAL+0.3ATR (blízko support, ale ne moc pod)
            # SELL: close mezi VAH-0.3ATR a VAH+0.5ATR (blízko resistance, ale ne moc nad)
            near_val = (val - atr_ * 0.5) <= curr["Close"] <= (val + atr_ * 0.3) and curr["Low"] <= val + atr_ * 0.5
            near_vah = (vah - atr_ * 0.3) <= curr["Close"] <= (vah + atr_ * 0.5) and curr["High"] >= vah - atr_ * 0.5
            # Value zone: long pod POC (discount), short nad POC (premium). POC = fair value.
            in_value_long = in_discount or curr["Close"] <= poc
            in_value_short = in_premium or curr["Close"] >= poc

            # LONG: RSI oversold (< 45) – kvalita nad kvantitou
            if in_value_long and near_val and is_bullish and curr["RSI"] < 45:
                if not self.use_smc or near_swing_low:
                    signal = "BUY"
                    reason = f"Range BUY @ VAL ({val:.2f})"
                    setup_type = "Mean_Reversion"
            if signal == "NEUTRAL" and in_value_long and (curr["Low"] <= curr["VWAP_Lower"]) and is_bullish and curr["RSI"] < 42:
                signal = "BUY"
                reason = "Range BUY @ VWAP Lower"
                setup_type = "Mean_Reversion"

            # SHORT: RSI overbought (> 55)
            if signal == "NEUTRAL" and in_value_short and near_vah and is_bearish and curr["RSI"] > 55:
                if not self.use_smc or near_swing_high:
                    signal = "SELL"
                    reason = f"Range SELL @ VAH ({vah:.2f})"
                    setup_type = "Mean_Reversion"
            if signal == "NEUTRAL" and in_value_short and (curr["High"] >= curr["VWAP_Upper"]) and is_bearish and curr["RSI"] > 58:
                signal = "SELL"
                reason = "Range SELL @ VWAP Upper"
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
            used_sl_mult = self.sl_atr * 1.5
            used_tp_rr = self.tp_rr
        else:
            used_sl_mult = self.sl_atr
            used_tp_rr = 1.5

        if signal == "BUY":
            sl_price = close - (atr * used_sl_mult)
            if setup_type == "Trend_Pullback":
                sl_price = min(sl_price, curr['Low'] - atr)
            if setup_type == "Mean_Reversion":
                # Forex mode: SL pod VWAP lower, crypto: SL pod VAL
                if self.forex_mode:
                    sl_price = min(sl_price, curr["VWAP_Lower"] - atr * 0.5)
                    risk = close - sl_price
                    # TP: VWAP (fair value) nebo min 1.5:1 R:R
                    tp_price = max(vwap, close + risk * 1.5)
                else:
                    # SL pod VAL, ale respektuj used_sl_mult (ne fixní 1.0)
                    sl_price = min(sl_price, val - atr * 0.5)
                    risk = close - sl_price
                    # TP: min 1.2:1 R:R (kvalitnější mean reversion)
                    min_reward = risk * 1.2
                    tp_price = max(vah, close + min_reward)
            else:
                tp_dist = (close - sl_price) * used_tp_rr
                tp_price = close + tp_dist

        elif signal == "SELL":
            sl_price = close + (atr * used_sl_mult)
            if setup_type == "Trend_Pullback":
                sl_price = max(sl_price, curr['High'] + atr)
            if setup_type == "Mean_Reversion":
                # Forex mode: SL nad VWAP upper, crypto: SL nad VAH
                if self.forex_mode:
                    sl_price = max(sl_price, curr["VWAP_Upper"] + atr * 0.5)
                    risk = sl_price - close
                    # TP: VWAP nebo min 1.5:1 R:R
                    tp_price = min(vwap, close - risk * 1.5)
                else:
                    # SL nad VAH, ale respektuj used_sl_mult
                    sl_price = max(sl_price, vah + atr * 0.5)
                    risk = sl_price - close
                    # TP: min 1.2:1 R:R
                    min_reward = risk * 1.2
                    tp_price = min(val, close - min_reward)
            else:
                tp_dist = (sl_price - close) * used_tp_rr
                tp_price = close - tp_dist

        # Min R:R 1.0 – skip jen ztrátové setupy (mean reversion u VAL/VAH často 1:1)
        min_rr = 1.0
        if signal == "BUY":
            risk = close - sl_price
            reward = tp_price - close
            rr = reward / risk if risk > 0 else 0
        elif signal == "SELL":
            risk = sl_price - close
            reward = close - tp_price
            rr = reward / risk if risk > 0 else 0
        else:
            rr = 2.0
        if rr < min_rr:
            return {'signal': 'NEUTRAL', 'reason': f'R:R {rr:.2f} < {min_rr}', 'rsi': float(curr['RSI']), 'adx': float(curr['ADX']), 'regime': self.last_regime}
            
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
