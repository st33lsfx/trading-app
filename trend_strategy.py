"""
Trend Following Strategy v1.0
=============================
Pro trending trhy (ADX >= 25):
- EMA crossover (8/21)
- Momentum confirmation (RSI direction)
- ATR-based SL/TP
- Trailing stop

Použití: Když ADX >= 25, trh má trend → následuj ho
"""

import pandas as pd
import numpy as np
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange


from ta.volume import VolumeWeightedAveragePrice

class TrendStrategy:
    """Trend Following strategie pro trending trhy (Upgraded 2026)."""
    
    def __init__(self, config=None):
        self.config = config or {}
        
        # HMA periods (Fast & Smooth)
        self.hma_fast = self.config.get('hma_fast', 9)   # Faster than EMA 8
        self.hma_slow = self.config.get('hma_slow', 21)
        
        # RSI settings
        self.rsi_period = 14
        
        # ADX threshold for trend confirmation
        self.adx_min = self.config.get('adx_min', 25)
        
        # Risk management
        self.atr_period = 14
        self.atr_sl_mult = self.config.get('atr_sl_mult', 2.0)
        self.atr_tp_mult = self.config.get('atr_tp_mult', 4.0)
        self.min_rr_ratio = self.config.get('min_rr_ratio', 2.0)

    def _calculate_wma(self, series, window):
        """Helper: Weighted Moving Average"""
        weights = np.arange(1, window + 1)
        return series.rolling(window).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

    def _calculate_hma(self, series, window):
        """Calculate Hull Moving Average (Reduces lag)"""
        half_length = int(window / 2)
        sqrt_length = int(np.sqrt(window))
        
        wma_half = self._calculate_wma(series, half_length)
        wma_full = self._calculate_wma(series, window)
        
        raw_hma = 2 * wma_half - wma_full
        return self._calculate_wma(raw_hma, sqrt_length)

    def add_indicators(self, df):
        """Přidej indikátory (HMA, VWAP, ADX, RSI, ATR)."""
        df = df.copy()
        
        # 1. VWAP (Institutional Value)
        # Requires High, Low, Close, Volume
        if 'Volume' in df.columns and df['Volume'].sum() > 0:
            try:
                vwap = VolumeWeightedAveragePrice(
                    high=df['High'], low=df['Low'], close=df["Close"], volume=df['Volume'], window=14
                )
                df['vwap'] = vwap.volume_weighted_average_price()
            except Exception:
                df['vwap'] = df['Close']
        else:
            # Fallback if no volume (e.g. some forex feeds)
            df['vwap'] = df['Close'] # Neutralizer
        
        # 2. HMA (Hull Moving Average) - Faster than EMA
        df['hma_fast'] = self._calculate_hma(df['Close'], self.hma_fast)
        df['hma_slow'] = self._calculate_hma(df['Close'], self.hma_slow)
        
        # RSI
        df['rsi'] = RSIIndicator(df['Close'], window=self.rsi_period).rsi()
        
        # ADX
        adx = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
        df['adx'] = adx.adx()
        df['di_plus'] = adx.adx_pos()
        df['di_minus'] = adx.adx_neg()
        
        # ATR
        df['atr'] = AverageTrueRange(df['High'], df['Low'], df['Close'], window=self.atr_period).average_true_range()
        
        return df
    
    def get_signal(self, df, config=None, major_trend="NEUTRAL"):
        """
        Získej trading signál (HMA Cross + VWAP Filter).
        """
        if len(df) < 30:
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Nedostatek dat", "rsi": 50}
        
        # Add indicators
        df = self.add_indicators(df)
        
        row = df.iloc[-1]
        prev = df.iloc[-2]
        
        current_price = row['Close']
        adx = row['adx']
        rsi = row['rsi']
        atr = row['atr']
        hma_fast = row['hma_fast']
        hma_slow = row['hma_slow']
        vwap = row['vwap']
        di_plus = row['di_plus']
        di_minus = row['di_minus']
        
        if pd.isna(adx) or pd.isna(rsi) or pd.isna(atr):
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Missing indicators", "rsi": 50}
        
        signal = "NEUTRAL"
        confidence = 0
        reason = ""
        sl = None
        tp = None
        filter_results = []
        
        # TREND STRENGTH CHECK
        if adx < self.adx_min:
            return {
                "signal": "NEUTRAL", 
                "confidence": 0, 
                "reason": f"Slabý trend (ADX {adx:.1f} < {self.adx_min})", 
                "rsi": rsi,
                "adx": adx
            }
        
        sl_distance = atr * self.atr_sl_mult
        tp_distance = atr * self.atr_tp_mult
        
        prev_bullish = prev['Close'] > prev['Open']
        prev_bearish = prev['Close'] < prev['Open']
        
        # === BUY CONDITION ===
        # 1. HMA Fast > HMA Slow (Trend Up)
        # 2. Price > VWAP (Institutional Bullish) - NEW 2026
        # 3. RSI > 50 (Momentum)
        # 4. Confirmation Candle
        if hma_fast > hma_slow and current_price > vwap and rsi > 50:
            if di_plus > di_minus and prev_bullish:
                signal = "BUY"
                confidence = 0.7 + (adx - self.adx_min) / 100
                sl = current_price - sl_distance
                tp = current_price + tp_distance
                reason = f"HMA Cross + VWAP Break: Price > VWAP, HMA Up, ADX {adx:.1f}"
                filter_results.append(f"✅ Price above VWAP (Institutional Value)")
                filter_results.append(f"✅ HMA Fast > Slow (Low Lag Trend)")
                filter_results.append(f"✅ Strong ADX ({adx:.1f})")
            else:
                 return {"signal": "NEUTRAL", "confidence": 0, "reason": "Waiting for DI+ or Candle", "rsi": rsi}

        # === SELL CONDITION ===
        # 1. HMA Fast < HMA Slow (Trend Down)
        # 2. Price < VWAP (Institutional Bearish) - NEW 2026
        # 3. RSI < 50
        # 4. Confirmation Candle
        elif hma_fast < hma_slow and current_price < vwap and rsi < 50:
            if di_minus > di_plus and prev_bearish:
                signal = "SELL"
                confidence = 0.7 + (adx - self.adx_min) / 100
                sl = current_price + sl_distance
                tp = current_price - tp_distance
                reason = f"HMA Cross + VWAP Break: Price < VWAP, HMA Down, ADX {adx:.1f}"
                filter_results.append(f"✅ Price below VWAP (Institutional Value)")
                filter_results.append(f"✅ HMA Fast < Slow (Low Lag Trend)")
                filter_results.append(f"✅ Strong ADX ({adx:.1f})")
            else:
                 return {"signal": "NEUTRAL", "confidence": 0, "reason": "Waiting for DI- or Candle", "rsi": rsi}
        
        # =============================================
        # R:R VALIDATION
        # =============================================
        if signal != "NEUTRAL" and sl and tp:
            risk = abs(current_price - sl)
            reward = abs(tp - current_price)
            rr_ratio = reward / risk if risk > 0 else 0
            
            if rr_ratio < self.min_rr_ratio:
                return {
                    "signal": "NEUTRAL",
                    "confidence": 0,
                    "reason": f"R:R {rr_ratio:.2f} < {self.min_rr_ratio} (skip)",
                    "rsi": rsi
                }
            
            filter_results.append(f"✅ R:R OK ({rr_ratio:.2f})")
        
        return {
            "signal": signal,
            "confidence": min(confidence, 1.0),
            "sl": sl,
            "tp": tp,
            "rsi": rsi,
            "adx": adx,
            "reason": reason,
            "filters": filter_results,
            "strategy": "TREND_FOLLOWING"
        }


# Singleton instance
_strategy_instance = None

def get_strategy(config=None):
    """Získej singleton instanci strategie."""
    global _strategy_instance
    if _strategy_instance is None:
        _strategy_instance = TrendStrategy(config)
    return _strategy_instance


if __name__ == "__main__":
    import yfinance as yf
    
    print("Testing Trend Strategy...")
    
    # Download test data
    ticker = "EURUSD=X"
    data = yf.download(ticker, period="1mo", interval="1h", progress=False)
    
    # Flatten columns
    if hasattr(data.columns, 'levels'):
        data.columns = data.columns.get_level_values(0)
    
    strategy = TrendStrategy()
    signal = strategy.get_signal(data)
    
    print(f"Ticker: {ticker}")
    print(f"Signal: {signal['signal']}")
    print(f"Confidence: {signal.get('confidence', 0):.2f}")
    print(f"RSI: {signal.get('rsi', 0):.1f}")
    print(f"ADX: {signal.get('adx', 0):.1f}")
    print(f"Reason: {signal.get('reason', '')}")
