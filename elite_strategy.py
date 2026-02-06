"""
Elite Strategie v2.0 (2026 Ultimate Hybrid + Volume Profile)
===========================================================
Kombinace "Absolutně nejlepších" indikátorů + Volume Profile dle QuantVPS & NAGA Academy 2026.
Určeno pro maximální ziskovost ve volatilních, do strany jdoucích i trendových fázích.

HLAVNÍ INDIKÁTORY (8-bodová Konfluence):
1. Hull Moving Average (HMA 9/21) - Rychlý směr trendu (nulový lag)
2. Supertrend (ATR 10, 3.0) - Filtr trendu & Dynamický Trailing Stop
3. ADX (14) - Síla trendu (>25 = Trend)
4. Parabolic SAR (0.02, 0.2) - Výstup & potvrzení obratu
5. Ichimoku Cloud - Support/Resistance & Twist cloudu
6. MACD (12,26,9) - Momentum signály
7. VWAP - Institucionální férová cena (Cena > VWAP = Bullish)
8. Volume Profile (POC/VAH/VAL) - Struktura trhu & Likvidita
   - Vstup do trendu: Průraz Value Area (VAH/VAL) s objemovým spikem
   - Support: Point of Control (POC) jako dynamický support/resistance

PRAVIDLA VSTUPU:
- ADX > 25 (Trend Mode Only)
- PŘÍSNÁ KONFLUENCE: Minimálně 4 z 8 indikátorů musí souhlasit.
- POTVRZENÍ OBJEMEM: Cena vzhledem k POC/VAH/VAL.

RISK MANAGEMENT:
- Dynamický Risk: 0.5% - 0.7% dle skóre konfluence.
- SL: Dynamický (dle ATR nebo Supertrend/POC levelu).
- TP: Otevřený interval s Trailing Stopem.
"""

import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, MACD, PSARIndicator
from ta.volatility import AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice


class EliteStrategy:
    """
    Elite Trading Strategie 2026
    Kombinuje top indikátory + Volume Profile pro vstupy s vysokou pravděpodobností.
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
        
        # === 7. VOLUME PROFILE ===
        self.vp_bins = 24  # Granularita pro VP

        # === RISK MANAGEMENT ===
        self.min_rr_ratio = self.config.get('min_rr_ratio', 2.0)
        self.min_confluence = self.config.get('min_confluence', 4)  # STRICT: Defaultně 4
        self.atr_sl_mult = self.config.get('atr_sl_mult', 2.0)
        
        # Interní stav
        self._has_real_vwap = False

    # =========================================================
    # VÝPOČET INDIKÁTORŮ
    # =========================================================

    def _calculate_wma(self, series, window):
        """Weighted Moving Average (Vážený klouzavý průměr)."""
        weights = np.arange(1, window + 1)
        return series.rolling(window).apply(
            lambda x: np.dot(x, weights) / weights.sum(), raw=True
        )

    def _calculate_hma(self, series, window):
        """Hull Moving Average - eliminuje zpoždění (lag)."""
        half_len = max(1, int(window / 2))
        sqrt_len = max(1, int(np.sqrt(window)))
        wma_half = self._calculate_wma(series, half_len)
        wma_full = self._calculate_wma(series, window)
        raw_hma = 2 * wma_half - wma_full
        return self._calculate_wma(raw_hma, sqrt_len)

    def _calculate_supertrend(self, df):
        """Výpočet Supertrendu (Trend + Směr)."""
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
        """Komponenty Ichimoku Cloudu."""
        high, low = df['High'], df['Low']
        
        tenkan = (high.rolling(self.ichi_tenkan).max() + low.rolling(self.ichi_tenkan).min()) / 2
        kijun = (high.rolling(self.ichi_kijun).max() + low.rolling(self.ichi_kijun).min()) / 2
        
        # Posun vpřed
        span_a = ((tenkan + kijun) / 2).shift(self.ichi_kijun)
        
        high_52 = high.rolling(self.ichi_senkou_b).max()
        low_52 = low.rolling(self.ichi_senkou_b).min()
        span_b = ((high_52 + low_52) / 2).shift(self.ichi_kijun)
        
        return span_a, span_b
        
    def _calculate_volume_profile(self, df):
        """Vypočítat POC, VAH, VAL."""
        if 'Volume' not in df.columns or df['Volume'].sum() == 0:
            return None
            
        # Použij recent window (posledních 50-100 svíček) pro relevanci
        lookback = min(len(df), 100)
        subset = df.tail(lookback)
        
        price_min = subset['Close'].min()
        price_max = subset['Close'].max()
        if price_min == price_max: return None
        
        range_size = price_max - price_min
        bin_size = range_size / self.vp_bins
        
        # Binning (Rozdělení do košů)
        bins = {}
        for idx, row in subset.iterrows():
            p = row['Close']
            v = row['Volume']
            bin_idx = int((p - price_min) / bin_size)
            bins[bin_idx] = bins.get(bin_idx, 0) + v
            
        # POC (Point of Control)
        if not bins: return None
        poc_bin = max(bins, key=bins.get)
        poc_price = price_min + (poc_bin + 0.5) * bin_size
        
        # Value Area (70% objemu)
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
            "total_vol": total_vol
        }

    def add_indicators(self, df):
        """Přidat všech 8 Elite indikátorů."""
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

        # ATR & RSI (Pomocné)
        df['atr'] = AverageTrueRange(df['High'], df['Low'], close, window=14).average_true_range()
        df['rsi'] = RSIIndicator(close, window=14).rsi()

        return df

    # =========================================================
    # SKÓROVÁNÍ KONFLUENCE (Jádro logiky)
    # =========================================================

    def _score_confluence(self, row, direction, vp_data):
        """
        Zkontroluje shodu všech 8 indikátorů.
        Returns: score (0-8), max_score, details
        """
        score = 0
        max_score = 8
        details = []
        indicators_used = []
        is_buy = (direction == "BUY")
        close = row['Close']

        # 1. HMA (Směr)
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

        # 2. Supertrend (Směr)
        st_ok = (row['st_direction'] == 1) if is_buy else (row['st_direction'] == -1)
        if st_ok:
            score += 1
            indicators_used.append("Supertrend")
            details.append(f"✅ Supertrend")
        else:
            details.append(f"❌ Supertrend")
            
        # 3. Parabolic SAR (Pozice)
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

        # 5. Ichimoku (Filtr Cloudu)
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

        # 6. VWAP (Institucionální cena)
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

        # 7. ADX DI (Směrová síla)
        di_ok = (row['di_plus'] > row['di_minus']) if is_buy else (row['di_minus'] > row['di_plus'])
        if di_ok:
            score += 1
            indicators_used.append("DI+/-")
            details.append(f"✅ DI+/-")
        else:
            details.append(f"❌ DI+/-")

        # 8. VOLUME PROFILE (Struktura)
        if vp_data:
            poc = vp_data['poc']
            vah = vp_data['vah']
            val = vp_data['val']
            
            # Logika: Průraz Value Area NEBO Odraz od POC
            # Pro Trend preferujeme Breakout nebo Cena > POC (Bull) / Cena < POC (Bear)
            
            if is_buy:
                # Bullish: Cena nad POC, ideálně proráží VAH
                vp_ok = close > poc
                if close > vah: # Silný Breakout
                    score += 1  # Bonus bod za breakout? Ne, striktně binární
                    details.append(f"✅ VP (Průraz VAH)")
                elif vp_ok:
                    details.append(f"✅ VP (>POC)")
                else:
                    details.append(f"❌ VP (<POC)")
                    vp_ok = False
            else:
                # Bearish
                vp_ok = close < poc
                if close < val:
                     details.append(f"✅ VP (Průraz VAL)")
                elif vp_ok:
                     details.append(f"✅ VP (<POC)")
                else:
                     details.append(f"❌ VP (>POC)")
                     vp_ok = False
                     
            if vp_ok:
                score += 1
                indicators_used.append("VolProfile")
        else:
            max_score -= 1
            details.append("⬜ VP (No Data)")

        return score, max_score, indicators_used, details

    # =========================================================
    # GENERACE SIGNÁLŮ
    # =========================================================

    def get_signal(self, df, config=None, major_trend="NEUTRAL"):
        """
        Získej Elite Signál.
        """
        if len(df) < 60:
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Inicializace...", "rsi": 50}

        df = self.add_indicators(df)
        row = df.iloc[-1]
        
        close = row['Close']
        adx = row['adx']
        atr = row['atr']
        rsi = row['rsi']
        
        # VP Calc
        vp_data = self._calculate_volume_profile(df)
        
        # 1. GATE: Síla Trendu (ADX)
        if adx < self.adx_min:
            return {
                "signal": "NEUTRAL", 
                "confidence": 0, 
                "reason": f"Slabý Trend (ADX {adx:.1f} < {self.adx_min})",
                "rsi": rsi, "adx": adx
            }

        # 2. URČENÍ SMĚRU (dle Supertrendu)
        direction = "BUY" if row['st_direction'] == 1 else "SELL"
        
        # 3. KONTROLA POTVRZOVACÍ SVÍČKY (Confirmation Candle)
        is_bullish = close > df.iloc[-1]['Open']
        if direction == "BUY" and not is_bullish:
             return {"signal": "NEUTRAL", "confidence": 0, "reason": "Čekám na Bullish svíčku", "rsi": rsi, "adx": adx}
        if direction == "SELL" and is_bullish:
             return {"signal": "NEUTRAL", "confidence": 0, "reason": "Čekám na Bearish svíčku", "rsi": rsi, "adx": adx}
             
        # 4. KONTROLA KONFLUENCE
        score, max_s, tools, details = self._score_confluence(row, direction, vp_data)
        
        required = min(self.min_confluence, max_s)
        if score < required:
            return {
                "signal": "NEUTRAL",
                "confidence": 0,
                "reason": f"Nízká Konfluence ({score}/{max_s})",
                "rsi": rsi, "adx": adx, "filters": details
            }
            
        # 5. RISK MANAGEMENT
        sl_base = row['supertrend']
        
        # POC Ochrana: Pokud je POC mezi Vstupem a SL, použij POC jako Support/Resistance
        if vp_data:
            poc = vp_data['poc']
            if direction == "BUY" and close > poc > sl_base:
                sl_base = poc # Přitáhni SL k POC
            elif direction == "SELL" and close < poc < sl_base:
                sl_base = poc

        # Validace Min/Max Vzdálenosti SL
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
            
        # Škálování Confidence
        confidence = 0.6 + (score/max_s * 0.3) + (min(adx, 50)/200)
        
        # Bonus pro Volume Spike
        recent_vol = df['Volume'].tail(3).mean()
        avg_vol = df['Volume'].mean()
        if avg_vol > 0 and recent_vol > (avg_vol * 1.5):
            confidence += 0.05
            details.append("⚡ Vol Spike")
        
        return {
            "signal": direction,
            "confidence": min(0.95, confidence),
            "sl": round(sl, 4),
            "tp": round(tp, 4),
            "rsi": rsi,
            "adx": adx,
            "reason": f"ELITE {direction}: Skóre {score}/{max_s}, ADX {adx:.0f}",
            "filters": details,
            "strategy": "ELITE_2026_VP",
            "indicators_used": tools
        }

if __name__ == "__main__":
    print("Elite Strategy (Integrovaný VP) načtena.")
