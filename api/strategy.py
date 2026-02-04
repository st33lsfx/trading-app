import yfinance as yf
import pandas as pd

class Strategy:
    def __init__(self, ticker):
        self.ticker = ticker

    def fetch_data(self, period="1mo", interval="1h"):
        """Fetch historical data from Yahoo Finance."""
        ticker_obj = yf.Ticker(self.ticker)
        df = ticker_obj.history(period=period, interval=interval)
        return df

    def calculate_indicators(self, df):
        """Calculate RSI, Fibonacci, and EMA levels."""
        # Simple Moving Average (SMA)
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        
        # EMA for Trend Filter
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # Rolling High/Low for Fibonacci (Lookback 50 candles)
        lookback = 50
        df['Roll_High'] = df['High'].rolling(window=lookback).max()
        df['Roll_Low'] = df['Low'].rolling(window=lookback).min()
        
        return df

    def get_signal(self, df):
        """
        Strategy:
        BUY if RSI < 30 (Oversold)
        Targets based on Fibonacci Retracement of the recent range.
        TP: 50% Retracement
        SL: Below Recent Low
        """
        if df.empty:
             return {"action": "NEUTRAL"}

        last = df.iloc[-1]
        rsi = last['RSI']
        close = last['Close']
        ema_200 = last.get('EMA_200', 0)
        high = last['Roll_High']
        low = last['Roll_Low']
        
        # 1. Trend Filter: Only Buy if Price > EMA 200 (Uptrend) or EMA not yet formed
        # If we want to be strict: 
        if ema_200 > 0 and close < ema_200:
             return {"action": "NEUTRAL", "reason": f"Downtrend (Price {close:.2f} < EMA {ema_200:.2f})", "rsi": rsi}
        
        # print(f"DEBUG: {self.ticker} | RSI: {rsi:.2f} | Close: {close:.2f} | High: {high:.2f} | Low: {low:.2f}")

        if rsi < 30:
            # Fibonacci Retracement Calculation (from Low to High)
            # Retracement levels: 0.236, 0.382, 0.5, 0.618
            # If we buy at 'close' (which is near Low because RSI < 30), 
            # we aim for a bounce back up towards the High.
            
            diff = high - low
            fib_50 = low + (diff * 0.5)
            # fib_618 = low + (diff * 0.618)
            
            # Dynamic TP: Aim for 50% retracement
            tp_price = fib_50
            
            # If TP is below/near current CLOSE, bump it
            if tp_price <= close * 1.01:
                 tp_price = close * 1.03
            
            # Dynamic SL: Below Low
            sl_price = low * 0.99 
            
            # If SL is above/near current CLOSE, fix it
            if sl_price >= close * 0.99:
                 sl_price = close * 0.97
            
            return {
                "action": "BUY",
                "tp": round(tp_price, 2),
                "sl": round(sl_price, 2),
                "rsi": rsi
            }
        
        elif rsi > 70:
             return {"action": "SELL"}
        
        return {"action": "NEUTRAL"}
