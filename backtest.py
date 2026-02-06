"""
Backtesting Module for Trading Bot
===================================
Simulates strategy on historical data to validate profitability.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from elite_strategy import EliteStrategy  # Updated import
from itertools import product


class Backtester:
    """
    Backtesting engine for Elite Volume Profile Strategy.
    """

    def __init__(self, strategy_config=None, initial_capital=1000.0, spread_pct=0.0001):
        """
        Initialize backtester.
        """
        # ELITE CONFIG
        self.config = strategy_config or {
            "rsi_buy": 60,
            "rsi_oversold": 40,
            "rsi_sell": 40,
            "rsi_overbought": 60,
            "adx_min": 25,
            "risk_reward": 2.0,
            "atr_sl_mult": 2.0,
            "max_risk_pct": 0.008,
            "min_confluence": 4,      # Standard Elite settings
            "trailing_stop": False,   # Elite uses fixed SL/TP or PSAR (handled in loop if needed)
        }
        self.initial_capital = initial_capital
        self.spread_pct = spread_pct

    def fetch_data(self, ticker, period="60d", interval="15m"):
        """
        Fetch historical data from Yahoo Finance.
        Elite Strategy defaults: 60d, 15m.
        """
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period=period, interval=interval)
            if df.empty:
                raise ValueError(f"No data returned for {ticker}")
            return df
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            return pd.DataFrame()

    def run(self, ticker, period="60d", interval="15m", config=None):
        """
        Run backtest on a single ticker.
        """
        if config:
            self.config.update(config)

        # Fetch data
        df = self.fetch_data(ticker, period, interval)
        if df.empty:
            return {"error": f"No data for {ticker}"}

        # Initialize strategy
        strategy = EliteStrategy(self.config)
        
        # Calculate indicators
        # EliteStrategy uses 'add_indicators' which returns DF
        try:
            df = strategy.add_indicators(df)
            # Calculate VP (needed for get_signal, but usually calculated inside get_signal on sliced DF)
            # pre-calculation of non-looking-forward indicators is fine.
        except Exception as e:
             return {"error": f"Indicator Calc Error: {e}"}

        # Remove NaN rows
        df = df.dropna()

        if len(df) < 60:
            return {"error": "Not enough data after indicator warmup"}

        # Simulate trades
        trades = self._simulate_trades(df, strategy)

        # Calculate metrics
        metrics = self._calculate_metrics(trades, df)

        return {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "config": self.config.copy(),
            "data_points": len(df),
            "start_date": df.index[0].strftime("%Y-%m-%d %H:%M") if hasattr(df.index[0], 'strftime') else str(df.index[0]),
            "end_date": df.index[-1].strftime("%Y-%m-%d %H:%M") if hasattr(df.index[-1], 'strftime') else str(df.index[-1]),
            **metrics,
            "trades": trades
        }

    def _simulate_trades(self, df, strategy):
        """
        Walk through data and simulate trades using EliteStrategy logic.
        """
        trades = []
        position = None 
        trailing_enabled = self.config.get('trailing_stop', False)
        
        # EliteStrategy needs ~60 bars warmup for some indicators
        min_lookback = 60

        for i in range(min_lookback, len(df)):
            current_candle = df.iloc[i]
            current_time = df.index[i]
            
            # If position open, check exits
            if position:
                high = current_candle['High']
                low = current_candle['Low']
                close = current_candle['Close']
                direction = position['direction']
                bars_held = i - position['entry_idx']
                
                # Check SL
                sl_hit = False
                if direction == "BUY" and low <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                    sl_hit = True
                elif direction == "SELL" and high >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                    sl_hit = True
                    
                # Check TP
                tp_hit = False
                if not sl_hit:
                    if direction == "BUY" and high >= position['tp']:
                        exit_price = position['tp']
                        exit_reason = "TP"
                        tp_hit = True
                    elif direction == "SELL" and low <= position['tp']:
                        exit_price = position['tp']
                        exit_reason = "TP"
                        tp_hit = True
                        
                # Time Exit (Safety)
                time_exit = False
                if not sl_hit and not tp_hit and bars_held > 100: # Max 100 bars for 15m
                    exit_price = close
                    exit_reason = "Time Exit"
                    time_exit = True
                    
                if sl_hit or tp_hit or time_exit:
                    entry = position['entry_price']
                    if direction == "BUY":
                        pnl = exit_price - entry
                    else:
                        pnl = entry - exit_price
                        
                    pnl_pct = (pnl / entry) * 100 - (self.spread_pct * 100)
                    
                    trades.append({
                        "entry_time": position['entry_time'],
                        "exit_time": current_time,
                        "entry_price": round(entry, 5),
                        "exit_price": round(exit_price, 5),
                        "pnl_pct": round(pnl_pct, 2),
                        "direction": direction,
                        "exit_reason": exit_reason,
                        "bars_held": bars_held
                    })
                    position = None
                    continue
            
            # Look for Entry
            if not position:
                # Pass sliced DF to get_signal (simulates real-time)
                # Optimization: Pass only last 100 candles to speed up VP calc
                start_slice = max(0, i-100)
                df_slice = df.iloc[start_slice:i+1].copy()
                
                # Use EliteStrategy.get_signal
                # Note: get_signal does indicator calc internally if needed, 
                # but we already added indicators to full DF. 
                # VP needs to be recalc-ed on the slice though.
                try:
                    signal = strategy.get_signal(df_slice)
                except:
                    continue
                    
                if signal['signal'] in ["BUY", "SELL"]:
                    entry_price = current_candle['Close']
                    direction = signal['signal']
                    
                    # Apply Slippage
                    if direction == "BUY": 
                        entry_price *= (1 + self.spread_pct)
                    else:
                        entry_price *= (1 - self.spread_pct)
                        
                    position = {
                        "entry_idx": i,
                        "entry_time": current_time,
                        "entry_price": entry_price,
                        "direction": direction,
                        "sl": signal['sl'],
                        "tp": signal['tp'],
                        "reason": signal['reason']
                    }
                    
        # Close any open position at end
        if position is not None:
            final_price = df.iloc[-1]['Close']
            direction = position['direction']
            entry = position['entry_price']

            if direction == "BUY":
                pnl = final_price - entry
            else:  # SELL
                pnl = entry - final_price

            pnl_pct = (pnl / entry) * 100 - self.spread_pct * 100

            trades.append({
                "entry_time": position['entry_time'],
                "exit_time": df.index[-1],
                "entry_price": round(entry, 5),
                "exit_price": round(final_price, 5),
                "sl": round(position['sl'], 5),
                "tp": round(position['tp'], 5),
                "pnl_pct": round(pnl_pct, 3),
                "direction": direction,
                "exit_reason": "End of Data",
                "bars_held": len(df) - 1 - position['entry_idx']
            })

        return trades

    def _calculate_metrics(self, trades, df):
        """
        Calculate comprehensive performance metrics from trades.
        """
        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "long_trades": 0,
                "short_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "calmar_ratio": 0.0,
                "recovery_factor": 0.0,
                "expectancy": 0.0,
                "avg_win_pct": 0.0,
                "avg_loss_pct": 0.0,
                "avg_bars_held": 0,
                "max_consecutive_wins": 0,
                "max_consecutive_losses": 0,
                "equity_curve": [],
                "exit_reasons": {}
            }

        # Basic counts
        total_trades = len(trades)
        pnls = [t['pnl_pct'] for t in trades]

        winning_trades = len([p for p in pnls if p > 0])
        losing_trades = len([p for p in pnls if p <= 0])

        # Long/Short breakdown
        long_trades = len([t for t in trades if t.get('direction') == 'BUY'])
        short_trades = len([t for t in trades if t.get('direction') == 'SELL'])
        long_wins = len([t for t in trades if t.get('direction') == 'BUY' and t['pnl_pct'] > 0])
        short_wins = len([t for t in trades if t.get('direction') == 'SELL' and t['pnl_pct'] > 0])

        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

        # Profit Factor
        gross_profit = sum([p for p in pnls if p > 0])
        gross_loss = abs(sum([p for p in pnls if p < 0]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Total Return (compounded)
        total_return_pct = sum(pnls)

        # Equity Curve (for drawdown and visualization)
        equity = [self.initial_capital]
        for pnl_pct in pnls:
            new_equity = equity[-1] * (1 + pnl_pct / 100)
            equity.append(new_equity)

        # Max Drawdown
        peak = equity[0]
        max_dd = 0
        for eq in equity:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # === NEW METRICS ===
        
        # Max Consecutive Wins/Losses
        max_cons_wins = 0
        max_cons_losses = 0
        current_wins = 0
        current_losses = 0
        
        for pnl in pnls:
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_cons_wins = max(max_cons_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_cons_losses = max(max_cons_losses, current_losses)

        # Sharpe Ratio (simplified - annualized)
        if len(pnls) > 1:
            returns = np.array(pnls) / 100
            avg_return = np.mean(returns)
            std_return = np.std(returns)

            trades_per_year = total_trades * (252 / 30) if total_trades > 0 else 1  # assuming 1mo period

            if std_return > 0:
                sharpe_ratio = (avg_return / std_return) * np.sqrt(trades_per_year)
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0

        # Calmar Ratio (return / max drawdown)
        calmar_ratio = total_return_pct / max_dd if max_dd > 0 else 0

        # Recovery Factor (total profit / max drawdown)
        recovery_factor = gross_profit / max_dd if max_dd > 0 else 0

        # Expectancy (average profit per trade)
        expectancy = sum(pnls) / total_trades if total_trades > 0 else 0

        # Average Win/Loss
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        # Risk/Reward Ratio (actual achieved)
        actual_rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        # Average bars held
        avg_bars = sum([t['bars_held'] for t in trades]) / total_trades if total_trades > 0 else 0

        # Exit reasons breakdown
        exit_reasons = {}
        for t in trades:
            reason = t.get('exit_reason', 'Unknown')
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        # Largest win/loss
        largest_win = max(pnls) if pnls else 0
        largest_loss = min(pnls) if pnls else 0

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "long_trades": long_trades,
            "short_trades": short_trades,
            "long_win_rate": round(long_wins / long_trades * 100, 1) if long_trades > 0 else 0,
            "short_win_rate": round(short_wins / short_trades * 100, 1) if short_trades > 0 else 0,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else 999.99,
            "total_return_pct": round(total_return_pct, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "calmar_ratio": round(calmar_ratio, 2),
            "recovery_factor": round(recovery_factor, 2),
            "expectancy": round(expectancy, 3),
            "avg_win_pct": round(avg_win, 3),
            "avg_loss_pct": round(avg_loss, 3),
            "actual_rr": round(actual_rr, 2),
            "avg_bars_held": round(avg_bars, 1),
            "max_consecutive_wins": max_cons_wins,
            "max_consecutive_losses": max_cons_losses,
            "largest_win_pct": round(largest_win, 3),
            "largest_loss_pct": round(largest_loss, 3),
            "exit_reasons": exit_reasons,
            "equity_curve": [round(e, 2) for e in equity]
        }

    def optimize(self, ticker, period="3mo", interval="5m", param_ranges=None):
        """
        Grid search optimization over strategy parameters.

        Args:
            ticker: Ticker to optimize on
            period: Data period
            interval: Candle interval
            param_ranges: Dict of param -> [values] to test

        Returns:
            List of results sorted by profit factor
        """
        if param_ranges is None:
            param_ranges = {
                "rsi_buy": [55, 58, 62],
                "rsi_oversold": [35, 38, 42],
                "adx_min": [25, 28, 32],
                "risk_reward": [1.5, 1.8, 2.2],
                "atr_sl_mult": [1.2, 1.5, 1.8]
            }

        # Fetch data once
        df = self.fetch_data(ticker, period, interval)
        if df.empty:
            return []

        # Pre-calculate indicators
        strategy = Strategy(ticker)
        df = strategy.calculate_indicators(df)
        df = df.dropna(subset=['EMA_200', 'RSI', 'MACD', 'ADX', 'ATR'])

        # Generate all combinations
        keys = list(param_ranges.keys())
        values = list(param_ranges.values())
        combinations = list(product(*values))

        results = []
        total = len(combinations)

        for idx, combo in enumerate(combinations):
            config = self.config.copy()
            for i, key in enumerate(keys):
                config[key] = combo[i]

            # Run backtest with this config
            self.config = config
            trades = self._simulate_trades(df, strategy)
            metrics = self._calculate_metrics(trades, df)

            results.append({
                "params": {keys[i]: combo[i] for i in range(len(keys))},
                **metrics
            })

            if (idx + 1) % 10 == 0:
                print(f"Optimization progress: {idx + 1}/{total}")

        # Sort by profit factor (or custom metric)
        results.sort(key=lambda x: x.get('profit_factor', 0), reverse=True)

        return results

    def walk_forward_analysis(self, ticker, train_period_days=30, test_period_days=15, 
                                total_periods=3, interval="5m", param_ranges=None):
        """
        Walk-forward analysis: optimize on training period, test on out-of-sample period.
        
        Args:
            ticker: Yahoo Finance ticker
            train_period_days: Days for optimization (in-sample)
            test_period_days: Days for testing (out-of-sample)
            total_periods: Number of walk-forward periods
            interval: Candle interval
            param_ranges: Parameters to optimize
            
        Returns:
            dict with walk-forward results
        """
        if param_ranges is None:
            param_ranges = {
                "rsi_buy": [55, 58, 62],
                "adx_min": [18, 22, 26],
                "risk_reward": [1.5, 2.0, 2.5]
            }
        
        # Fetch all data first
        total_days = (train_period_days + test_period_days) * total_periods
        period_str = f"{min(total_days + 10, 60)}d"  # Yahoo limit for 5m data
        
        df = self.fetch_data(ticker, period_str, interval)
        if df.empty:
            return {"error": f"No data for {ticker}"}
        
        # Calculate indicators once
        strategy = Strategy(ticker)
        df = strategy.calculate_indicators(df)
        df = df.dropna(subset=['EMA_200', 'RSI', 'MACD', 'ADX', 'ATR'])
        
        if len(df) < 500:
            return {"error": "Not enough data for walk-forward analysis"}
        
        results = []
        all_oos_trades = []  # Out-of-sample trades
        
        # Calculate candles per day (approximate)
        if interval == "5m":
            candles_per_day = 288
        elif interval == "15m":
            candles_per_day = 96
        elif interval == "1h":
            candles_per_day = 24
        else:
            candles_per_day = 288
        
        train_candles = train_period_days * candles_per_day
        test_candles = test_period_days * candles_per_day
        
        for period_num in range(total_periods):
            # Calculate indices for this period
            start_idx = period_num * test_candles
            train_end_idx = start_idx + train_candles
            test_end_idx = train_end_idx + test_candles
            
            if test_end_idx > len(df):
                break
            
            # Split data
            train_df = df.iloc[start_idx:train_end_idx].copy()
            test_df = df.iloc[train_end_idx:test_end_idx].copy()
            
            if len(train_df) < 250 or len(test_df) < 50:
                continue
            
            # Optimize on training data
            best_config = self._optimize_on_df(train_df, strategy, param_ranges)
            
            # Test on out-of-sample data
            self.config.update(best_config)
            test_trades = self._simulate_trades(test_df, strategy)
            test_metrics = self._calculate_metrics(test_trades, test_df)
            
            # Also run training metrics for comparison
            train_trades = self._simulate_trades(train_df, strategy)
            train_metrics = self._calculate_metrics(train_trades, train_df)
            
            results.append({
                "period": period_num + 1,
                "train_start": train_df.index[0].strftime("%Y-%m-%d") if hasattr(train_df.index[0], 'strftime') else str(train_df.index[0]),
                "test_start": test_df.index[0].strftime("%Y-%m-%d") if hasattr(test_df.index[0], 'strftime') else str(test_df.index[0]),
                "best_params": best_config,
                "train_trades": train_metrics['total_trades'],
                "train_win_rate": train_metrics['win_rate'],
                "train_pf": train_metrics['profit_factor'],
                "train_return": train_metrics['total_return_pct'],
                "test_trades": test_metrics['total_trades'],
                "test_win_rate": test_metrics['win_rate'],
                "test_pf": test_metrics['profit_factor'],
                "test_return": test_metrics['total_return_pct'],
                "robustness": test_metrics['profit_factor'] / train_metrics['profit_factor'] if train_metrics['profit_factor'] > 0 else 0
            })
            
            all_oos_trades.extend(test_trades)
        
        if not results:
            return {"error": "Could not complete walk-forward analysis"}
        
        # Aggregate out-of-sample metrics
        oos_pnls = [t['pnl_pct'] for t in all_oos_trades]
        oos_wins = len([p for p in oos_pnls if p > 0])
        oos_gross_profit = sum([p for p in oos_pnls if p > 0])
        oos_gross_loss = abs(sum([p for p in oos_pnls if p < 0]))
        
        return {
            "ticker": ticker,
            "periods": results,
            "total_oos_trades": len(all_oos_trades),
            "oos_win_rate": round(oos_wins / len(all_oos_trades) * 100, 2) if all_oos_trades else 0,
            "oos_profit_factor": round(oos_gross_profit / oos_gross_loss, 2) if oos_gross_loss > 0 else 999.99,
            "oos_total_return": round(sum(oos_pnls), 2),
            "avg_robustness": round(np.mean([r['robustness'] for r in results]), 2),
            "consistency": sum(1 for r in results if r['test_pf'] > 1) / len(results) * 100
        }
    
    def _optimize_on_df(self, df, strategy, param_ranges):
        """Quick optimization on pre-calculated DataFrame."""
        keys = list(param_ranges.keys())
        values = list(param_ranges.values())
        combinations = list(product(*values))
        
        best_pf = 0
        best_config = {}
        
        for combo in combinations:
            config = self.config.copy()
            for i, key in enumerate(keys):
                config[key] = combo[i]
            
            self.config = config
            trades = self._simulate_trades(df, strategy)
            
            if trades:
                pnls = [t['pnl_pct'] for t in trades]
                gross_profit = sum([p for p in pnls if p > 0])
                gross_loss = abs(sum([p for p in pnls if p < 0]))
                pf = gross_profit / gross_loss if gross_loss > 0 else 0
                
                if pf > best_pf:
                    best_pf = pf
                    best_config = {keys[i]: combo[i] for i in range(len(keys))}
        
        return best_config

    def multi_ticker_test(self, tickers, period="3mo", interval="5m"):
        """
        Run backtest on multiple tickers and aggregate results.

        Args:
            tickers: List of Yahoo Finance tickers
            period: Data period
            interval: Candle interval

        Returns:
            dict with individual and aggregated results
        """
        individual_results = []
        all_trades = []

        for ticker in tickers:
            print(f"Testing {ticker}...")
            result = self.run(ticker, period, interval)

            if 'error' not in result:
                individual_results.append(result)
                all_trades.extend(result.get('trades', []))

        if not all_trades:
            return {"error": "No successful backtests"}

        # Aggregate metrics
        all_pnls = [t['pnl_pct'] for t in all_trades]
        total_trades = len(all_trades)
        winning = len([p for p in all_pnls if p > 0])

        gross_profit = sum([p for p in all_pnls if p > 0])
        gross_loss = abs(sum([p for p in all_pnls if p < 0]))

        return {
            "tickers_tested": len(individual_results),
            "tickers": [r['ticker'] for r in individual_results],
            "total_trades": total_trades,
            "win_rate": round(winning / total_trades * 100, 2) if total_trades > 0 else 0,
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999.99,
            "total_return_pct": round(sum(all_pnls), 2),
            "avg_return_per_trade": round(sum(all_pnls) / total_trades, 3) if total_trades > 0 else 0,
            "individual_results": individual_results
        }


# Quick test
if __name__ == "__main__":
    bt = Backtester()

    # Single ticker test
    print("=" * 50)
    print("Running backtest on EURUSD...")
    print("=" * 50)

    result = bt.run("EURUSD=X", period="3mo", interval="5m")

    if 'error' in result:
        print(f"Error: {result['error']}")
    else:
        print(f"\nResults for {result['ticker']}:")
        print(f"  Period: {result['start_date']} to {result['end_date']}")
        print(f"  Data points: {result['data_points']}")
        print(f"  Total trades: {result['total_trades']}")
        print(f"  Win rate: {result['win_rate']}%")
        print(f"  Profit factor: {result['profit_factor']}")
        print(f"  Total return: {result['total_return_pct']}%")
        print(f"  Max drawdown: {result['max_drawdown_pct']}%")
        print(f"  Sharpe ratio: {result['sharpe_ratio']}")
        print(f"  Expectancy: {result['expectancy']}% per trade")

        print(f"\n  Last 5 trades:")
        for t in result['trades'][-5:]:
            print(f"    {t['entry_time']} -> {t['exit_time']}: {t['pnl_pct']:+.2f}% ({t['exit_reason']})")
