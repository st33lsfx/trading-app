"""
Bulk Historical Learning Script
===============================
Spustí simulaci obchodů na 1-leté historii pro 50+ aktiv.
Výsledky uloží do Learning Engine, čímž "naučí" bota:
- Která aktiva jsou zisková (profit factor > 1.0)
- Která aktiva blokovat (blacklist)
- Win rate a statistiky pro dashboard

Author: Bot (DeepMind)
Date: 2026-02-05
"""

import yfinance as yf
import pandas as pd
import warnings
import time
from datetime import datetime
from learning_engine import get_learning_engine
from hybrid_strategy import HybridStrategy

warnings.filterwarnings('ignore')

# === KONFIGURACE ===
PERIOD = "1y"
INTERVAL = "1h"
ASSETS = [
    # Forex Majors
    'EURUSD=X', 'GBPUSD=X', 'JPY=X', 'AUDUSD=X', 'NZDUSD=X', 'USDCAD=X', 'USDCHF=X',
    
    # Forex Minors
    'EURGBP=X', 'EURJPY=X', 'GBPJPY=X', 'AUDJPY=X', 'CHFJPY=X', 'NZDJPY=X',
    'GBPAUD=X', 'EURAUD=X', 'AUDNZD=X', 'CADJPY=X', 'GBPCHF=X', 'EURCHF=X',
    'USDMXN=X',
    
    # Crypto
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'ADA-USD', 
    'DOGE-USD', 'LTC-USD', 'DOT-USD', 'AVAX-USD', 'LINK-USD',
    
    # Commodities (Futures)
    'GC=F', 'SI=F', 'CL=F',
    
    # Tech Stocks
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'AMD', 'NFLX', 'INTC'
]

def simulate_trades(ticker, strategy, engine):
    """
    Simuluje obchody RYCHLE (předvypočítané indikátory).
    """
    print(f"📥 Downloading {ticker} ({PERIOD}, {INTERVAL})...")
    try:
        df = yf.download(ticker, period=PERIOD, interval=INTERVAL, progress=False, auto_adjust=True)
        if len(df) < 200:
            print(f"❌ {ticker}: Not enough data")
            return
            
        # Flatten columns
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.get_level_values(0)
            
        # === 1. PŘEDVÝPOČET INDIKÁTORŮ ===
        # Využijeme metody strategií pro přidání sloupců do DF
        df = strategy.mean_reversion.add_indicators(df)
        df = strategy.trend_following.add_indicators(df) 
        # (TrendStrategy přidá ADX, EMA, RSI.. MeanReversion přidá BB, RSI.. 
        #  Pokud se RSI jmenuje stejně, přepíše se, to nevadí, je to stejné RSI 14)

        # Drop NaN (kvůli indikátorům)
        df.dropna(inplace=True)
        
        # === 2. RYCHLÁ ITERACE ===
        trades_count = 0
        wins = 0
        pnl_total = 0.0
        
        position = None
        
        # Získat indexy sloupců pro rychlý přístup
        # (Použijeme itertuples pro rychlost)
        
        # Parametry (default z configu)
        rsi_oversold = 40
        rsi_overbought = 60
        adx_threshold = 25
        
        # Pro iteraci potřebujeme předchozí řádek
        prev_row = None
        
        for row in df.itertuples():
            if prev_row is None:
                prev_row = row
                continue
                
            current_price = row.Close
            
            # --- MANAGE POSITION ---
            if position:
                exit_price = None
                reason = ""
                
                # Check SL/TP
                if position['direction'] == 'BUY':
                    if row.Low <= position['sl']:
                        exit_price = position['sl']
                        reason = "SL"
                    elif row.High >= position['tp']:
                        exit_price = position['tp']
                        reason = "TP"
                else: # SELL
                    if row.High >= position['sl']:
                        exit_price = position['sl']
                        reason = "SL"
                    elif row.Low <= position['tp']:
                        exit_price = position['tp']
                        reason = "TP"
                
                # Timeout (100 bars)
                if not exit_price and (row.Index - position['entry_time']).total_seconds() / 3600 > 100:
                    exit_price = current_price
                    reason = "TIMEOUT"
                
                if exit_price:
                    # Calc PnL
                    if position['direction'] == 'BUY':
                        pnl_pct = (exit_price - position['entry']) / position['entry'] * 100
                    else:
                        pnl_pct = (position['entry'] - exit_price) / position['entry'] * 100
                    
                    cash_pnl = 1000 * (pnl_pct / 100)
                    
                    engine.record_trade(
                        ticker=ticker,
                        pnl=cash_pnl,
                        direction=position['direction'],
                        entry_price=position['entry'],
                        exit_price=exit_price,
                        exit_reason=reason
                    )
                    
                    trades_count += 1
                    if cash_pnl > 0: wins += 1
                    pnl_total += cash_pnl
                    position = None
            
            # --- OPEN POSITION ---
            if position is None:
                adx = getattr(row, 'adx', 0)
                signal = None
                sl = None
                tp = None
                
                # Confirmation candles
                prev_bullish = prev_row.Close > prev_row.Open
                prev_bearish = prev_row.Close < prev_row.Open
                
                # === REGIME DETECTION ===
                if adx < adx_threshold:
                    # MEAN REVERSION LOGIC
                    bb_lower = getattr(row, 'bb_lower', 0)
                    bb_upper = getattr(row, 'bb_upper', 0)
                    rsi = getattr(row, 'rsi', 50)
                    atr = getattr(row, 'atr', 0)
                    
                    sl_dist = atr * 2.0
                    tp_dist = atr * 3.0 # 1.5 R:R
                    
                    # BUY: Low <= BB Lower + RSI < 40 + Bullish Confirm
                    if row.Low <= bb_lower * 1.003 and rsi < rsi_oversold and prev_bullish:
                        signal = "BUY"
                        sl = current_price - sl_dist
                        tp = current_price + tp_dist
                    
                    # SELL: High >= BB Upper + RSI > 60 + Bearish Confirm
                    elif row.High >= bb_upper * 0.997 and rsi > rsi_overbought and prev_bearish:
                        signal = "SELL"
                        sl = current_price + sl_dist
                        tp = current_price - tp_dist
                        
                else:
                    # TREND LOGIC
                    ema_fast = getattr(row, 'ema_fast', 0)
                    ema_slow = getattr(row, 'ema_slow', 0)
                    rsi = getattr(row, 'rsi', 50)
                    di_plus = getattr(row, 'di_plus', 0)
                    di_minus = getattr(row, 'di_minus', 0)
                    atr = getattr(row, 'atr', 0)
                    
                    sl_dist = atr * 2.0
                    tp_dist = atr * 4.0 # 2.0 R:R
                    
                    # BUY: Fast > Slow + DI+ > DI- + RSI > 50 + Confirm
                    if ema_fast > ema_slow and di_plus > di_minus and rsi > 50 and prev_bullish:
                        signal = "BUY"
                        sl = current_price - sl_dist
                        tp = current_price + tp_dist
                        
                    # SELL: Fast < Slow + DI- > DI+ + RSI < 50 + Confirm
                    elif ema_fast < ema_slow and di_minus > di_plus and rsi < 50 and prev_bearish:
                        signal = "SELL"
                        sl = current_price + sl_dist
                        tp = current_price - tp_dist
                
                if signal:
                    position = {
                        'direction': signal,
                        'entry': current_price,
                        'sl': sl,
                        'tp': tp,
                        'entry_time': row.Index
                    }
            
            prev_row = row
            
        # Log result
        win_rate = (wins/trades_count*100) if trades_count > 0 else 0
        if trades_count > 0:
            print(f"✅ {ticker}: {trades_count} trades, WR {win_rate:.1f}%, PnL ${pnl_total:.2f}")
        else:
            print(f"⚠️ {ticker}: No trades found")

    except Exception as e:
        print(f"❌ {ticker}: Error {e}")


def main():
    print("🚀 Starting OPTIMIZED Bulk Learning...")
    print(f"Assets: {len(ASSETS)}")
    print(f"Period: {PERIOD}, Interval: {INTERVAL}")
    print("="*60)
    
    engine = get_learning_engine()
    strategy = HybridStrategy()
    
    start_time = time.time()
    
    for ticker in ASSETS:
        simulate_trades(ticker, strategy, engine)
        
    duration = time.time() - start_time
    print(f"⏱️ Finished in {duration:.1f}s")
    
    # Final Save
    engine._save_data()
    print("="*60)
    print("🏁 Learning Complete! Data saved to learning_data.json")

if __name__ == "__main__":
    main()
