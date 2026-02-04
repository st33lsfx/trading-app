
import yfinance as yf
import pandas as pd
import numpy as np
from mean_reversion_strategy import MeanReversionStrategy

def run_backtest():
    print("🚀 Spouštím Smart Backtest (posledních 30 dní)...")
    
    # Portfolio aktiv (MEGA TEST - 30+ aktiv)
    tickers = [
        # Forex (Majors)
        "GBPUSD=X", "EURUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X",
        # Forex (Crosses)
        "EURGBP=X", "GBPJPY=X", "EURJPY=X",
        # Tech Stocks
        "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "AMD", "NFLX", "INTC",
        # Indices (Tracking ETFs)
        "SPY", "QQQ", "DIA", "IWM",  # S&P500, Nasdaq, Dow, Russell
        # Crypto
        "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD",
        # Commodities
        "GC=F", "SI=F", "CL=F" # Gold, Silver, Oil
    ]
    
    # Konfigurace (Agresivní)
    config = {
        "rsi_oversold": 55,
        "rsi_overbought": 45,
        "atr_sl_mult": 2.5,
        "min_rr_ratio": 1.2,
        "use_volatility_filter": True,
    }
    
    strategy = MeanReversionStrategy(config)
    
    total_pnl = 0
    total_trades = 0
    wins = 0
    trade_log = []
    
    # Stáhnout VIX pro sentiment filtr
    vix_df = yf.download("^VIX", period="1mo", interval="1h", progress=False)
    
    for ticker in tickers:
        print(f"\nAnalyzuji {ticker}...")
        df = yf.download(ticker, period="1mo", interval="1h", progress=False)
        
        if df.empty:
            continue
            
        # Fix multi-index columns if needed
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        position = None # None or {'type': 'BUY', 'price': 100, 'sl': 90, 'tp': 110}
        
        for i in range(50, len(df)):
            # Simulation slice
            window = df.iloc[:i+1]
            current_bar = window.iloc[-1]
            current_time = current_bar.name
            price = current_bar['Close']
            
            # Check VIX Filter
            try:
                # Find matching time in VIX (approx)
                current_vix = vix_df.iloc[i]['Close'] if i < len(vix_df) else 20
                if current_vix > 28: # Too much fear
                    continue
            except:
                pass

            # Manage Position
            if position:
                # Check SL/TP
                if position['type'] == 'BUY':
                    if current_bar['Low'] <= position['sl']:
                        pnl = (position['sl'] - position['price']) * position['size']
                        total_pnl += pnl
                        total_trades += 1
                        wins += 1 if pnl > 0 else 0
                        trade_log.append(f"🔴 SL Hit {ticker}: ${pnl:.2f}")
                        position = None
                    elif current_bar['High'] >= position['tp']:
                        pnl = (position['tp'] - position['price']) * position['size']
                        total_pnl += pnl
                        total_trades += 1
                        wins += 1 if pnl > 0 else 0
                        trade_log.append(f"🟢 TP Hit {ticker}: ${pnl:.2f}")
                        position = None
                continue
                
            # Look for Entry
            signal = strategy.get_signal(window)
            if signal['signal'] == 'BUY':
                # Entry
                # Velikost pozice: risk $25 na obchod (simulace)
                risk_per_share = price - signal['sl']
                if risk_per_share <= 0: continue
                
                size = 25 / risk_per_share # Fixed risk $25
                
                position = {
                    'type': 'BUY',
                    'price': price,
                    'sl': signal['sl'],
                    'tp': signal['tp'],
                    'size': size
                }
                # trade_log.append(f"Entry BUY {ticker} @ {price:.2f}")

    print("\n" + "="*40)
    print(f"📊 VÝSLEDEK BACKTESTU (30 DNÍ)")
    print("="*40)
    print(f"Celkový zisk: ${total_pnl:.2f} (cca {total_pnl*23:.0f} CZK)")
    print(f"Počet obchodů: {total_trades}")
    if total_trades > 0:
        print(f"Win Rate: {(wins/total_trades)*100:.1f}%")
        print(f"Průměrný zisk na obchod: ${total_pnl/total_trades:.2f}")
    else:
        print("Žádné obchody.")
    print("="*40)

if __name__ == "__main__":
    run_backtest()
