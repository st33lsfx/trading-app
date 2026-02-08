"""
Adaptive Backtest Engine with Walk-Forward Optimization
=====================================================
Features:
- Rolling Window Optimization (Train/Test Split)
- Grid Search for Best Parameters (ADX Threshold, SL Multiplier)
- Performance Metrics (Sharpe, Profit Factor, Max DD)
"""

import pandas as pd
import numpy as np
import yfinance as yf
from itertools import product
from adaptive_vp_strategy import AdaptiveStrategy
# import matplotlib.pyplot as plt # Removed to avoid dependency issues

class AdaptiveBacktester:
    def __init__(self, ticker, start_date, end_date, interval="1h"):
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.interval = interval
        self.df = None
        
    def fetch_data(self):
        print(f"Fetching {self.ticker} data...")
        self.df = yf.download(self.ticker, start=self.start_date, end=self.end_date, interval=self.interval, progress=False, auto_adjust=True, multi_level_index=False)
        
        # Fallback for older/newer yfinance versions
        if isinstance(self.df.columns, pd.MultiIndex):
            self.df.columns = self.df.columns.droplevel(1)
            
        self.df.dropna(inplace=True)
        print(f"Loaded {len(self.df)} candles.")
        return self.df
        
    def _run_single_pass(self, df, params):
        """Runs strategy on a specific dataframe slice with specific params."""
        strategy = AdaptiveStrategy(config=params)
        
        # Pre-calc indicators for speed
        df = strategy.add_indicators(df)
        df.dropna(inplace=True)
        
        balance = 10000.0 # Starting capital
        position = None # {'type': 'BUY'/'SELL', 'entry': price, 'sl': price, 'tp': price}
        trades = []
        equity_curve = []
        
        for i in range(50, len(df)):
            # Simulation Window: Feed history up to i
            # To optimize, we assume indicators are already correct (no look-ahead bias if using proper libraries)
            # VP needs re-calc every step or every N steps. For speed, we might re-calc VP every 4h?
            # Let's trust get_signal handles logic. To speed up, we pass slice.
            
            # NOTE: Passing full DF slice is SLOW for big backtests. 
            # We will pass a window for VP calc.
            window_size = params.get('vp_lookback', 96)
            if i < window_size: continue
            
            current_slice = df.iloc[i-window_size:i+1]
            curr_bar = df.iloc[i]
            
            # Check Exit First
            if position:
                pnl = 0
                exit_reason = ""
                price = curr_bar['Close'] # Simplified fill at Close
                if position['type'] == 'BUY':
                    if curr_bar['Low'] <= position['sl']:
                        pnl = (position['sl'] - position['entry']) * position['size']
                        exit_reason = "SL"
                    elif curr_bar['High'] >= position['tp']:
                        pnl = (position['tp'] - position['entry']) * position['size']
                        exit_reason = "TP"
                else: # SELL
                    if curr_bar['High'] >= position['sl']:
                        pnl = (position['entry'] - position['sl']) * position['size']
                        exit_reason = "SL"
                    elif curr_bar['Low'] <= position['tp']:
                        pnl = (position['entry'] - position['tp']) * position['size']
                        exit_reason = "TP"
                        
                if exit_reason:
                    balance += pnl
                    trades.append({'pnl': pnl, 'reason': exit_reason, 'exit_time': df.index[i]})
                    position = None
            
            # Check Entry
            if not position:
                sig = strategy.get_signal(current_slice)
                if sig['signal'] in ['BUY', 'SELL']:
                    risk_per_trade = balance * 0.02 # 2% risk
                    stop_dist = abs(curr_bar['Close'] - sig['sl'])
                    if stop_dist > 0:
                        size = risk_per_trade / stop_dist
                        position = {
                            'type': sig['signal'],
                            'entry': curr_bar['Close'],
                            'sl': sig['sl'],
                            'tp': sig['tp'],
                            'size': size
                        }
            
            equity_curve.append(balance)
            
        return trades, balance, equity_curve

    def walk_forward_optimization(self, train_months=3, test_months=1):
        """
        Optimization Loop:
        1. Select 3 months Train data -> Find best Params (Grid Search)
        2. Apply best Params to next 1 month Test data
        3. Slide window forward
        """
        if self.df is None: self.fetch_data()
        
        # Grid to search (Widened Range for Optimization)
        param_grid = {
            'adx_threshold': [15, 20, 25, 30, 40],
            'sl_atr_mult': [1.0, 1.5, 2.0, 3.0, 4.0],
            'tp_rr_ratio': [1.5, 2.0, 3.0]
        }
        keys, values = zip(*param_grid.items())
        combinations = [dict(zip(keys, v)) for v in product(*values)]
        
        # Split logic (simplified by index for speed)
        # Assuming 1h candles -> ~720 per month
        candles_per_month = 24 * 30 
        train_len = train_months * candles_per_month
        test_len = test_months * candles_per_month
        
        total_len = len(self.df)
        p = 0
        final_trades = []
        
        while p + train_len + test_len < total_len:
            train_df = self.df.iloc[p : p+train_len].copy()
            test_df = self.df.iloc[p+train_len : p+train_len+test_len].copy()
            
            print(f"--- WFO Step: Train [{train_df.index[0]} to {train_df.index[-1]}] | Test [{test_df.index[0]} to {test_df.index[-1]}] ---")
            
            # Optimize on Train
            best_score = -9999
            best_params = None
            
            for params in combinations:
                trades, bal, _ = self._run_single_pass(train_df, params)
                # Score: Profit Factor * Log(Trades)
                if not trades: score = 0
                else:
                    wins = sum(t['pnl'] for t in trades if t['pnl'] > 0)
                    losses = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
                    pf = wins / losses if losses > 0 else 1.0
                    score = pf * len(trades) # Simple custom metric
                
                if score > best_score:
                    best_score = score
                    best_params = params
            
            print(f"Best Params Found: {best_params} (Score: {best_score:.2f})")
            
            # Run Test (Out of Sample)
            test_trades, _, _ = self._run_single_pass(test_df, best_params)
            final_trades.extend(test_trades)
            
            p += test_len # Slide window
            
        return final_trades

if __name__ == "__main__":
    # Example Run (Adjusted for Yahoo 730d limit from 2026)
    # Use last 12 months: Jan 2025 - Jan 2026
    bt = AdaptiveBacktester("BTC-USD", "2025-01-01", "2026-01-01", interval="1h")
    trades = bt.walk_forward_optimization()
    
    # Summary
    if trades:
        total_pnl = sum(t['pnl'] for t in trades)
        wins = len([t for t in trades if t['pnl'] > 0])
        print(f"\n=== FINAL RESULTS (Walk-Forward) ===")
        print(f"Total Trades: {len(trades)}")
        print(f"Win Rate: {wins/len(trades)*100:.1f}%")
        print(f"Total PnL: ${total_pnl:.2f}")

        # ASCII Equity Curve
        equity = [10000]
        curr = 10000
        for t in trades:
            curr += t['pnl']
            equity.append(curr)
        
        print("\n=== Equity Curve (ASCII) ===")
        max_val = max(equity)
        min_val = min(equity)
        range_val = max_val - min_val
        if range_val == 0: range_val = 1
        
        # Downsample to 50 points
        step = max(1, len(equity) // 50)
        sampled = equity[::step]
        
        for val in sampled:
            pos = int((val - min_val) / range_val * 40)
            print(f"{val:8.0f} |" + "#" * pos)
    else:
        print("No trades generated.")
