"""
Robust Backtest Engine (Walk-Forward + Monte Carlo)
===================================================
A professional-grade backtesting suite for the Elite Adaptive Strategy.

Features:
1. Walk-Forward Optimization (WFO): Train on X months, Test on Y months, Roll forward.
2. Monte Carlo Simulation: 1000+ shuffles of trade sequence to estimate risk of ruin.
3. Realistic Simulation: Spread, Slippage, Fees.
"""

import pandas as pd
import numpy as np
import yfinance as yf
import random
from itertools import product
from datetime import timedelta
import time
from elite_adaptive_strategy import EliteAdaptiveStrategy

class RobustBacktester:
    def __init__(self, ticker, start_date, end_date, interval="15m", capital=10000):
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.interval = interval
        self.capital = capital
        self.df = None
        
        # Costs
        self.fee_pct = 0.0006 # 0.06% per trade (Binance Taker)
        self.slippage_pct = 0.0002 # 0.02% slippage est
        self.spread_pct = 0.0001 # 0.01% spread est
        
    def fetch_data(self):
        print(f"📥 Fetching {self.ticker} ({self.start_date} to {self.end_date})...")
        try:
            self.df = yf.download(
                self.ticker, 
                start=self.start_date, 
                end=self.end_date, 
                interval=self.interval, 
                progress=False,
                auto_adjust=False  # Keep raw OHLC
            )
            
            # Fix multi-index if present (yfinance update)
            if isinstance(self.df.columns, pd.MultiIndex):
                self.df.columns = self.df.columns.droplevel(1)
            
            # Simple validation
            if self.df.empty:
                print("⚠️ Error: Empty DataFrame returned.")
                return False
                
            self.df.dropna(inplace=True)
            print(f"✅ Loaded {len(self.df)} candles.")
            return True
        except Exception as e:
            print(f"❌ Data Fetch Error: {e}")
            return False

    def run_pass(self, df_slice, params, initial_capital=10000):
        """
        Runs a single backtest pass on a dataframe slice.
        Returns: (trades_list, final_equity, equity_curve)
        """
        strategy = EliteAdaptiveStrategy(config=params)
        
        # Calculate indicators once (Vectorized for speed)
        # Note: Strategy must be careful not to look ahead. 
        # add_indicators uses simple rolling windows, so it is safe provided we iterate chronologically.
        df = strategy.add_indicators(df_slice)
        df = df.dropna()
        
        balance = initial_capital
        position = None # {'type': 'BUY'/'SELL', 'entry': float, 'sl': float, 'tp': float, 'size': float}
        trades = []
        equity_curve = [balance]
        
        # Iterate candles
        # We start after lookbacks valid
        start_idx = max(strategy.vp_lookback_bars, 200)
        if len(df) <= start_idx:
            return [], balance, []
            
        # We'll use a sliding window for the strategy to calculate VP correctly if needed,
        # but our Strategy class handles VP calculation on passed DF. 
        # CAUTION: calling get_signal(df.iloc[:i]) inside loop is O(N^2).
        # Optimization: We only re-calc VP every X bars or use the 'last_vp' caching if class supports it.
        # For 'Elite' precision, we DO strict slicing but optimize by checking signal only every candle.
        # To make WFO feasible in <60s, we will cheat slightly:
        # We will assume VP levels calculated at start of day persist for the day (Session VP).
        
        # Faster Loop:
        # We pre-calculate 'static' indicators. 
        # The dynamic part is VP. computed once per day? 
        # EliteStrategy uses Rolling VP. We will limit re-calc to every 4 hours (16 bars of 15m) for speed.
        
        last_vp_calc = 0
        cached_vp = None
        
        # Convert to records for speed
        records = df.to_dict('records')
        times = df.index
        
        for i in range(start_idx, len(records)):
            curr = records[i]
            prev = records[i-1]
            timestamp = times[i]
            
            # 1. Manage Open Position
            if position:
                pnl = 0
                exit_reason = ""
                price = curr['Close']
                
                # Check SL/TP (Hit in High/Low range)
                if position['type'] == 'BUY':
                    if curr['Low'] <= position['sl']:
                        price = position['sl'] # Slippage applied later
                        pnl = (price - position['entry']) * position['size']
                        exit_reason = "SL"
                    elif curr['High'] >= position['tp']:
                        price = position['tp']
                        pnl = (price - position['entry']) * position['size']
                        exit_reason = "TP"
                elif position['type'] == 'SELL':
                    if curr['High'] >= position['sl']:
                        price = position['sl']
                        pnl = (position['entry'] - price) * position['size']
                        exit_reason = "SL"
                    elif curr['Low'] <= position['tp']:
                        price = position['tp']
                        pnl = (position['entry'] - price) * position['size']
                        exit_reason = "TP"
                
                if exit_reason:
                    # Apply costs
                    trade_val = position['entry'] * position['size']
                    cost = trade_val * (self.fee_pct + self.slippage_pct + self.spread_pct) * 2 # Entry + Exit
                    
                    net_pnl = pnl - cost
                    balance += net_pnl
                    trades.append({
                        'time': timestamp,
                        'type': position['type'],
                        'result': 'WIN' if net_pnl > 0 else 'LOSS',
                        'pnl': net_pnl,
                        'reason': exit_reason
                    })
                    position = None
            
            # 2. Check for Entry (if no position)
            if not position:
                # Optimized Strategy Call:
                # We construct a mini-df or pass full df with index?
                # Passing full df.iloc for every bar is too slow.
                # We will rely on pre-calc indicators in 'curr'. 
                # BUT Strategy.get_signal calls logic that requires VP.
                # We will re-calc VP only every 4 hours (16 bars).
                
                if (i - last_vp_calc) >= 16 or cached_vp is None:
                    # Create slice for VP
                    vp_slice = pd.DataFrame(records[i-strategy.vp_lookback_bars:i]) # Slice list -> DF is slow, but better than iloc on huge DF
                    # We need columns match. 
                    if not vp_slice.empty:
                        vp_slice.columns = df.columns # Restore cols
                        # Actually creating DF from list of dicts is slow.
                        # Better: Use the main DF with iloc, but limited scope.
                        # df.iloc[i-Lookback:i]
                        cached_vp = strategy._calculate_composite_vp(df.iloc[i-strategy.vp_lookback_bars:i])
                    last_vp_calc = i
                
                # Manual Signal Logic (Replicating Strategy.get_signal for speed, using cached VP)
                # This ensures we don't instantiate Strategy class 50k times.
                
                if cached_vp:
                    sig = 'NEUTRAL'
                    sl = 0
                    tp = 0
                    
                    # Core Logic Variables
                    adx = curr['ADX']
                    vwap = curr['VWAP']
                    is_trend = adx > params['adx_threshold']
                    
                    poc = cached_vp['POC']
                    vah = cached_vp['VAH']
                    val = cached_vp['VAL']
                    
                    close_px = curr['Close']
                    ema200 = curr['EMA_200']
                    
                    # Helper: DI Direction Confirmation
                    di_bullish = curr['DIP'] > curr['DIM']
                    di_bearish = curr['DIM'] > curr['DIP']

                    # TREND
                    if is_trend:
                        # BUY
                        if close_px > ema200 and close_px > vwap and di_bullish:
                            # Breakout > VAH
                            if prev['Close'] < vah and curr['Close'] > vah:
                                sig = 'BUY'
                            # Pullback to VWAP
                            elif abs(curr['Low'] - vwap) < (curr['ATR']*0.5) and curr['Close'] > curr['Open']:
                                sig = 'BUY'
                        # SELL
                        elif close_px < ema200 and close_px < vwap and di_bearish:
                            # Breakdown < VAL
                            if prev['Close'] > val and curr['Close'] < val:
                                sig = 'SELL'
                            # Pullback
                            elif abs(curr['High'] - vwap) < (curr['ATR']*0.5) and curr['Close'] < curr['Open']:
                                sig = 'SELL'
                    
                    # RANGE (Mean Reversion) - Strict ADX < 18
                    elif adx < 18:
                        # Buy at VAL
                        # VAL Support + Oversold + DI Bullish
                        if abs(curr['Low'] - val) < (curr['ATR']*0.5) and curr['Close'] > curr['Open']:
                            if curr['RSI'] < 40 and di_bullish:
                                sig = 'BUY'
                        # Sell at VAH
                        # VAH Resistance + Overbought + DI Bearish
                        elif abs(curr['High'] - vah) < (curr['ATR']*0.5) and curr['Close'] < curr['Open']:
                             if curr['RSI'] > 60 and di_bearish:
                                sig = 'SELL'
                    
                    if sig != 'NEUTRAL':
                         # Risk Sizing
                         risk_pct = 0.02 # 2% fixed
                         risk_amt = balance * risk_pct
                         atr = curr['ATR']
                         
                         sl_mult = params['sl_atr']
                         
                         if sig == 'BUY':
                             sl = close_px - (atr * sl_mult)
                             tp = close_px + ((close_px - sl) * params['tp_rr'])
                         else:
                             sl = close_px + (atr * sl_mult)
                             tp = close_px - ((sl - close_px) * params['tp_rr'])
                             
                         dist = abs(close_px - sl)
                         if dist > 0:
                             size = risk_amt / dist
                             position = {
                                 'type': sig, 'entry': close_px, 'sl': sl, 'tp': tp, 'size': size
                             }

            equity_curve.append(balance)
            
        return trades, balance, equity_curve

    def walk_forward_optimization(self, train_months=3, test_months=1):
        """
        Performs WFO.
        """
        if self.df is None: self.fetch_data()
        
            # Optimizing Grid for higher win rate
        param_grid = {
            'adx_threshold': [25, 30, 35],
            'sl_atr': [2.0, 3.0],
            'tp_rr': [1.5, 2.0]
        }
        
        # Fixed params for 1h timeframe
        fixed_params = {
            'vp_lookback': 72, # 3 days of 1h data
            'vwap_window': 24, # 1 day of 1h data
        }
        
        # Generate combos
        keys, values = zip(*param_grid.items())
        combinations = [dict(zip(keys, v)) for v in product(*values)]
        
        # Convert months to approx bars (1h -> 720 bars/month)
        bars_per_month = 720
        train_len = train_months * bars_per_month
        test_len = test_months * bars_per_month
        
        total_bars = len(self.df)
        cursor = 0
        
        wfo_trades = []
        equity = [self.capital]
        curr_balance = self.capital
        
        print(f"\n🚀 Starting Walk-Forward Optimization (Train: {train_months}m, Test: {test_months}m)")
        print(f"Total Data: {total_bars} bars (~{total_bars/2880:.1f} months)")
        
        step_count = 0
        while cursor + train_len + test_len < total_bars:
            step_count += 1
            train_start = cursor
            train_end = cursor + train_len
            test_start = train_end
            test_end = min(test_start + test_len, total_bars)
            
            train_slice = self.df.iloc[train_start:train_end]
            test_slice = self.df.iloc[test_start:test_end]
            
            # --- OPTIMIZATION PHASE ---
            best_score = -999
            best_params = combinations[0]
            
            # We run optimization on subset. To save time, we might skip full grid if huge.
            # Here grid is 3*3*3 = 27 combos. Fast enough.
            
            for params in combinations:
                # Merge fixed params
                run_params = {**params, **fixed_params}
                trades, bal, _ = self.run_pass(train_slice, run_params, initial_capital=10000)
                # Score = Profit Factor * Sqrt(Trades)
                if not trades: score = 0
                else:
                     wins = sum(t['pnl'] for t in trades if t['pnl'] > 0)
                     losses = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
                     pf = wins / losses if losses > 1 else 1.0
                     score = pf *  np.sqrt(len(trades))
                
                if score > best_score:
                    best_score = score
                    best_params = params
            
            print(f"Step {step_count}: Best {best_params} (Score: {best_score:.2f}) -> Testing...")
            
            # --- TESTING PHASE ---
            # Run simulation on unknown data with optimized params
            best_run_params = {**best_params, **fixed_params}
            trades_oos, bal_oos, _ = self.run_pass(test_slice, best_run_params, initial_capital=curr_balance)
            
            if trades_oos:
                wfo_trades.extend(trades_oos)
                curr_balance += sum(t['pnl'] for t in trades_oos)
            
            cursor += test_len
            
        return wfo_trades, curr_balance

    def monte_carlo_simulation(self, trades, runs=1000):
        """
        Runs Monte Carlo simulation on the trade list to estimate risk.
        """
        if not trades: return
        
        pnls = [t['pnl'] for t in trades]
        final_balances = []
        max_drawdowns = []
        
        print(f"\n🎲 Running Monte Carlo ({runs} runs)...")
        
        for _ in range(runs):
            shuffled = random.sample(pnls, len(pnls))
            path = [self.capital]
            curr = self.capital
            dd = 0
            peak = self.capital
            
            for pnl in shuffled:
                curr += pnl
                path.append(curr)
                if curr > peak: peak = curr
                drawdown = (peak - curr) / peak
                if drawdown > dd: dd = drawdown
                
            final_balances.append(curr)
            max_drawdowns.append(dd)
            
        # Stats
        avg_bal = np.mean(final_balances)
        worst_dd = np.max(max_drawdowns)
        ruin_prob = sum(1 for b in final_balances if b < (self.capital * 0.5)) / runs # Ruin = 50% loss
        
        print(f"Monte Carlo Results:")
        print(f"  Avg Final Equity: ${avg_bal:.2f}")
        print(f"  Worst Case DD: {worst_dd*100:.2f}%")
        print(f"  Risk of Ruin (50% Loss): {ruin_prob*100:.1f}%")

if __name__ == "__main__":
    # Settings
    TICKER = "BTC-USD"
    # Backtest last 729 days (Yahoo limit for 1h is 730 days)
    START = (pd.Timestamp.now() - pd.DateOffset(days=729)).strftime('%Y-%m-%d')
    END = pd.Timestamp.now().strftime('%Y-%m-%d')
    
    # Use 1h for long-term WFO (Yahoo limitation)
    INTERVAL = "1h"
    bt = RobustBacktester(TICKER, START, END, interval=INTERVAL)
    
    # Adjust Strategy Config for 1h (1 day = 24 bars, not 96)
    # We pass this into the WFO optimization loop or strategy init?
    # The WFO loop uses 'combinations' of params. We need to inject fixed params too.
    # We will modify the WFO to accept 'fixed_params'.
    
    # Actually, let's just run it. The default lookbacks (96) will be ~4 days on 1h. 
    # That is acceptable for VWAP/VP (Weekly profile?).
    # Let's override for "Daily" equivalent: 24 bars.
    
    # 1. Run Walk-Forward
    # We need to hack the WFO method to pass base config? 
    # Or just rely on defaults for now since we can't easily injection without rewriting class.
    # Wait, simple fix: Update the class defaults in `elite_adaptive_strategy.py`? 
    # No, better to patch `run_pass` in `robust_backtest.py` or just let it be "Multi-Day VWAP".
    
    # Let's update `run_pass` to merge params.
    trades, final_bal = bt.walk_forward_optimization(train_months=3, test_months=1)
    
    # 2. Results
    print("\n" + "="*40)
    print("           FINAL RESULTS            ")
    print("="*40)
    
    if trades:
        total_pnl = sum(t['pnl'] for t in trades)
        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] <= 0]
        
        wr = len(wins) / len(trades) * 100
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = np.mean([abs(t['pnl']) for t in losses]) if losses else 0
        pf = (sum(t['pnl'] for t in wins) / abs(sum(t['pnl'] for t in losses))) if losses else 999
        
        print(f"Trades: {len(trades)}")
        print(f"Win Rate: {wr:.2f}%")
        print(f"Profit Factor: {pf:.2f}")
        print(f"Avg Win: ${avg_win:.2f} | Avg Loss: ${avg_loss:.2f}")
        print(f"Total PnL: ${total_pnl:.2f}")
        print(f"Return: {(final_bal - 10000)/10000 * 100:.2f}%")
        
        # 3. Validation
        bt.monte_carlo_simulation(trades)
        
    else:
        print("No trades executed.")
