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


class TrendStrategy:
    """Trend Following strategie pro trending trhy."""
    
    def __init__(self, config=None):
        self.config = config or {}
        
        # EMA periods
        self.ema_fast = self.config.get('ema_fast', 8)
        self.ema_slow = self.config.get('ema_slow', 21)
        
        # RSI settings
        self.rsi_period = 14
        self.rsi_trend_threshold = 50  # Above 50 = bullish, below = bearish
        
        # ADX threshold for trend confirmation
        self.adx_min = self.config.get('adx_min', 25)
        
        # Risk management
        self.atr_period = 14
        self.atr_sl_mult = self.config.get('atr_sl_mult', 2.0)
        self.atr_tp_mult = self.config.get('atr_tp_mult', 4.0)  # R:R 2:1
        
        # Minimum R:R ratio
        self.min_rr_ratio = self.config.get('min_rr_ratio', 2.0)
    
    def add_indicators(self, df):
        """Přidej indikátory pro trend following."""
        df = df.copy()
        
        # EMAs
        df['ema_fast'] = EMAIndicator(df['Close'], window=self.ema_fast).ema_indicator()
        df['ema_slow'] = EMAIndicator(df['Close'], window=self.ema_slow).ema_indicator()
        
        # RSI
        df['rsi'] = RSIIndicator(df['Close'], window=self.rsi_period).rsi()
        
        # ADX
        adx = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
        df['adx'] = adx.adx()
        df['di_plus'] = adx.adx_pos()
        df['di_minus'] = adx.adx_neg()
        
        # ATR
        df['atr'] = AverageTrueRange(df['High'], df['Low'], df['Close'], window=self.atr_period).average_true_range()
        
        # Trend direction from EMA
        df['ema_trend'] = np.where(df['ema_fast'] > df['ema_slow'], 'UP', 'DOWN')
        
        # EMA crossover detection
        df['ema_cross_up'] = (df['ema_fast'] > df['ema_slow']) & (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1))
        df['ema_cross_down'] = (df['ema_fast'] < df['ema_slow']) & (df['ema_fast'].shift(1) >= df['ema_slow'].shift(1))
        
        return df
    
    def get_signal(self, df, config=None, major_trend="NEUTRAL"):
        """
        Získej trading signál pro trend following.
        
        Returns:
            dict s klíči: signal, confidence, sl, tp, rsi, reason, filters
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
        ema_fast = row['ema_fast']
        ema_slow = row['ema_slow']
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
        
        # =============================================
        # TREND STRENGTH CHECK
        # =============================================
        if adx < self.adx_min:
            return {
                "signal": "NEUTRAL", 
                "confidence": 0, 
                "reason": f"Slabý trend (ADX {adx:.1f} < {self.adx_min})", 
                "rsi": rsi,
                "adx": adx
            }
        
        # =============================================
        # SIGNAL DETECTION - EMA CROSSOVER + MOMENTUM
        # =============================================
        
        sl_distance = atr * self.atr_sl_mult
        tp_distance = atr * self.atr_tp_mult
        
        # BUY SIGNAL CONDITIONS:
        # 1. EMA fast > EMA slow (uptrend)
        # 2. DI+ > DI- (bullish directional movement)
        # 3. RSI > 50 (bullish momentum)
        # 4. Confirmation: předchozí svíčka bullish
        
        prev_bullish = prev['Close'] > prev['Open']
        prev_bearish = prev['Close'] < prev['Open']
        
        if ema_fast > ema_slow and di_plus > di_minus and rsi > 50:
            if prev_bullish:
                signal = "BUY"
                confidence = 0.6 + (adx - self.adx_min) / 100  # Higher ADX = higher confidence
                sl = current_price - sl_distance
                tp = current_price + tp_distance
                reason = f"Trend BUY: EMA cross up, ADX {adx:.1f}, RSI {rsi:.1f}"
                filter_results.append(f"✅ Strong uptrend (ADX {adx:.1f})")
                filter_results.append(f"✅ Bullish momentum (RSI {rsi:.1f})")
                filter_results.append(f"✅ Confirmation candle (bullish)")
            else:
                return {"signal": "NEUTRAL", "confidence": 0, "reason": "⏳ Čekám na bullish confirmation", "rsi": rsi}
        
        # SELL SIGNAL CONDITIONS:
        # 1. EMA fast < EMA slow (downtrend)
        # 2. DI- > DI+ (bearish directional movement)
        # 3. RSI < 50 (bearish momentum)
        # 4. Confirmation: předchozí svíčka bearish
        
        elif ema_fast < ema_slow and di_minus > di_plus and rsi < 50:
            if prev_bearish:
                signal = "SELL"
                confidence = 0.6 + (adx - self.adx_min) / 100
                sl = current_price + sl_distance
                tp = current_price - tp_distance
                reason = f"Trend SELL: EMA cross down, ADX {adx:.1f}, RSI {rsi:.1f}"
                filter_results.append(f"✅ Strong downtrend (ADX {adx:.1f})")
                filter_results.append(f"✅ Bearish momentum (RSI {rsi:.1f})")
                filter_results.append(f"✅ Confirmation candle (bearish)")
            else:
                return {"signal": "NEUTRAL", "confidence": 0, "reason": "⏳ Čekám na bearish confirmation", "rsi": rsi}
        
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
    
    strategy = TrendStrategy()
    signal = strategy.get_signal(data)
    
    print(f"Ticker: {ticker}")
    print(f"Signal: {signal['signal']}")
    print(f"Confidence: {signal.get('confidence', 0):.2f}")
    print(f"RSI: {signal.get('rsi', 0):.1f}")
    print(f"ADX: {signal.get('adx', 0):.1f}")
    print(f"Reason: {signal.get('reason', '')}")
