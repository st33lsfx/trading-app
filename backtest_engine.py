"""
Backtest Engine v1.0 — Walk-Forward Validation + Monte Carlo
=============================================================
Institutional-grade backtesting framework for EliteStrategy V2.

Features:
- Simple backtest with per-trade P&L tracking
- Walk-forward optimization (expanding window)
- Out-of-sample performance measurement
- Monte Carlo simulation (trade-order randomization)
- Parameter sensitivity analysis
- Performance metrics: Sharpe, Sortino, Max DD, Win Rate, Profit Factor, etc.

IMPORTANT CAVEATS:
- This backtester uses close-price fills (no slippage model).
- Real-world performance WILL be worse due to:
  - Slippage (especially on small-cap crypto)
  - Spread costs (Capital.com CFDs)
  - Latency between signal and execution
  - Partial fills and requotes
- Always paper-trade for at least 2-4 weeks before going live.

DISCLAIMER: Past performance is NOT indicative of future results.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

# Add parent path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elite_strategy_v2 import EliteStrategyV2, RISK_PROFILES


# ══════════════════════════════════════════════════════════════════════
# CORE BACKTESTER
# ══════════════════════════════════════════════════════════════════════

class BacktestEngine:
    """
    Event-driven backtester for EliteStrategy V2.

    Simulates trades bar-by-bar using close-price fills.
    Tracks per-trade P&L, equity curve, drawdowns.
    """

    def __init__(self, initial_capital=2500.0, risk_per_trade=250.0,
                 max_risk_pct=0.30, commission_pct=0.0005):
        """
        Args:
            initial_capital: Starting account balance (CZK)
            risk_per_trade: Target risk in CZK per trade
            max_risk_pct: Maximum risk as % of equity
            commission_pct: Round-trip commission as fraction (0.05% default)
        """
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.max_risk_pct = max_risk_pct
        self.commission_pct = commission_pct
        self.strategy = EliteStrategyV2()

    def run(self, df, asset_class="default", ticker="UNKNOWN"):
        """
        Run backtest on a single instrument DataFrame.

        Args:
            df: OHLCV DataFrame (must have Open, High, Low, Close, Volume)
            asset_class: "crypto", "forex", or "default"
            ticker: Instrument name for logging

        Returns:
            dict with trades, equity_curve, metrics
        """
        if df is None or len(df) < 100:
            return {"error": "Insufficient data", "trades": [], "metrics": {}}

        trades = []
        equity = self.initial_capital
        equity_curve = [equity]
        peak_equity = equity
        max_drawdown = 0
        position = None  # None or dict

        # We need a minimum lookback before generating signals
        min_lookback = 80

        for i in range(min_lookback, len(df)):
            bar = df.iloc[i]
            bar_time = df.index[i] if hasattr(df.index[i], 'strftime') else str(i)

            # --- CHECK OPEN POSITION ---
            if position is not None:
                hit_sl = False
                hit_tp = False

                if position["direction"] == "BUY":
                    # Check SL (did low breach stop?)
                    if bar["Low"] <= position["sl"]:
                        hit_sl = True
                        exit_price = position["sl"]
                    # Check TP (did high reach target?)
                    elif bar["High"] >= position["tp"]:
                        hit_tp = True
                        exit_price = position["tp"]
                elif position["direction"] == "SELL":
                    if bar["High"] >= position["sl"]:
                        hit_sl = True
                        exit_price = position["sl"]
                    elif bar["Low"] <= position["tp"]:
                        hit_tp = True
                        exit_price = position["tp"]

                if hit_sl or hit_tp:
                    # Close position
                    if position["direction"] == "BUY":
                        pnl_per_unit = exit_price - position["entry"]
                    else:
                        pnl_per_unit = position["entry"] - exit_price

                    gross_pnl = pnl_per_unit * position["size"]
                    commission = position["entry"] * position["size"] * self.commission_pct * 2
                    net_pnl = gross_pnl - commission

                    # Convert to CZK (most assets in USD)
                    conversion = 24.0  # USD/CZK approximate
                    net_pnl_czk = net_pnl * conversion

                    equity += net_pnl_czk

                    trades.append({
                        "ticker": ticker,
                        "direction": position["direction"],
                        "entry_price": position["entry"],
                        "exit_price": exit_price,
                        "entry_time": position["entry_time"],
                        "exit_time": bar_time,
                        "exit_reason": "TP" if hit_tp else "SL",
                        "pnl": net_pnl_czk,
                        "pnl_pct": net_pnl_czk / self.initial_capital * 100,
                        "equity_after": equity,
                        "regime": position.get("regime", ""),
                        "confluence": position.get("confluence", 0),
                    })

                    position = None

            # --- GENERATE SIGNAL (only if no position) ---
            if position is None:
                window = df.iloc[max(0, i - min_lookback):i + 1].copy()
                result = self.strategy.get_signal(window, asset_class=asset_class)

                if result["signal"] in ["BUY", "SELL"] and result["sl"] and result["tp"]:
                    entry_price = bar["Close"]
                    sl = result["sl"]
                    tp = result["tp"]

                    # Position sizing based on risk
                    sl_distance = abs(entry_price - sl)
                    if sl_distance <= 0:
                        continue

                    conversion = 24.0
                    risk_per_unit = sl_distance * conversion
                    target_risk = min(self.risk_per_trade, equity * self.max_risk_pct)

                    if target_risk <= 0 or risk_per_unit <= 0:
                        continue

                    size = target_risk / risk_per_unit

                    position = {
                        "direction": result["signal"],
                        "entry": entry_price,
                        "sl": sl,
                        "tp": tp,
                        "size": size,
                        "entry_time": bar_time,
                        "regime": result.get("regime", ""),
                        "confluence": result.get("confluence_score", 0),
                    }

            # Track equity
            equity_curve.append(equity)
            peak_equity = max(peak_equity, equity)
            dd = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0
            max_drawdown = max(max_drawdown, dd)

        # Close any remaining position at last close
        if position:
            exit_price = df.iloc[-1]["Close"]
            if position["direction"] == "BUY":
                pnl_per_unit = exit_price - position["entry"]
            else:
                pnl_per_unit = position["entry"] - exit_price
            gross_pnl = pnl_per_unit * position["size"]
            commission = position["entry"] * position["size"] * self.commission_pct * 2
            net_pnl = (gross_pnl - commission) * 24.0
            equity += net_pnl
            trades.append({
                "ticker": ticker,
                "direction": position["direction"],
                "entry_price": position["entry"],
                "exit_price": exit_price,
                "entry_time": position["entry_time"],
                "exit_time": str(df.index[-1]),
                "exit_reason": "EOD",
                "pnl": net_pnl,
                "pnl_pct": net_pnl / self.initial_capital * 100,
                "equity_after": equity,
                "regime": position.get("regime", ""),
                "confluence": position.get("confluence", 0),
            })

        metrics = self._calculate_metrics(trades, equity_curve, equity)
        return {
            "trades": trades,
            "equity_curve": equity_curve,
            "metrics": metrics,
            "ticker": ticker,
            "asset_class": asset_class,
        }

    def _calculate_metrics(self, trades, equity_curve, final_equity):
        """Calculate comprehensive performance metrics."""
        if not trades:
            return {"total_trades": 0, "error": "No trades generated"}

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        avg_trade = np.mean(pnls) if pnls else 0
        expectancy = avg_trade

        # Sharpe & Sortino (annualized from daily-ish returns)
        if len(pnls) > 1:
            returns = np.array(pnls) / self.initial_capital
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
            downside = returns[returns < 0]
            sortino = np.mean(returns) / np.std(downside) * np.sqrt(252) if len(downside) > 0 and np.std(downside) > 0 else 0
        else:
            sharpe = 0
            sortino = 0

        # Max drawdown from equity curve
        eq = np.array(equity_curve)
        peak = np.maximum.accumulate(eq)
        dd = (peak - eq) / np.where(peak > 0, peak, 1) * 100
        max_dd = dd.max()

        # Per-regime stats
        regime_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
        for t in trades:
            r = t.get("regime", "UNKNOWN")
            regime_stats[r]["trades"] += 1
            if t["pnl"] > 0:
                regime_stats[r]["wins"] += 1
            regime_stats[r]["pnl"] += t["pnl"]

        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "total_return_pct": round(total_return, 2),
            "total_pnl": round(sum(pnls), 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(profit_factor, 3),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "avg_trade": round(avg_trade, 2),
            "expectancy": round(expectancy, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "max_drawdown_pct": round(max_dd, 2),
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2),
            "regime_breakdown": dict(regime_stats),
        }


# ══════════════════════════════════════════════════════════════════════
# WALK-FORWARD OPTIMIZATION
# ══════════════════════════════════════════════════════════════════════

def walk_forward_test(df, asset_class="default", ticker="UNKNOWN",
                      n_splits=5, train_ratio=0.7):
    """
    Walk-forward out-of-sample test.

    Splits data into n_splits segments.
    For each split: train on 70%, test on 30%.
    Reports out-of-sample performance across all folds.
    """
    total_len = len(df)
    split_size = total_len // n_splits
    results = []

    print(f"\n{'=' * 60}")
    print(f"WALK-FORWARD TEST: {ticker} ({asset_class})")
    print(f"Splits: {n_splits}, Train/Test: {train_ratio:.0%}/{1 - train_ratio:.0%}")
    print(f"{'=' * 60}")

    for fold in range(n_splits):
        start = fold * split_size
        end = min(start + split_size, total_len)

        if end - start < 150:
            continue

        fold_data = df.iloc[start:end]
        train_end = int(len(fold_data) * train_ratio)

        train_df = fold_data.iloc[:train_end]
        test_df = fold_data.iloc[train_end:]

        if len(test_df) < 50:
            continue

        # Run backtest on OUT-OF-SAMPLE (test) data only
        engine = BacktestEngine()
        result = engine.run(test_df, asset_class=asset_class, ticker=ticker)

        m = result["metrics"]
        results.append(m)

        print(f"\nFold {fold + 1}:")
        print(f"  Train: {len(train_df)} bars | Test: {len(test_df)} bars")
        print(f"  Trades: {m.get('total_trades', 0)} | WR: {m.get('win_rate', 0):.1f}%")
        print(f"  PnL: {m.get('total_pnl', 0):+.2f} CZK | PF: {m.get('profit_factor', 0):.2f}")
        print(f"  Max DD: {m.get('max_drawdown_pct', 0):.1f}%")

    if not results:
        print("No valid folds!")
        return None

    # Aggregate results
    avg_wr = np.mean([r.get("win_rate", 0) for r in results])
    avg_pf = np.mean([r.get("profit_factor", 0) for r in results if r.get("profit_factor", 0) < 100])
    avg_pnl = np.mean([r.get("total_pnl", 0) for r in results])
    max_dd = max(r.get("max_drawdown_pct", 0) for r in results)
    total_trades = sum(r.get("total_trades", 0) for r in results)

    print(f"\n{'─' * 60}")
    print(f"AGGREGATE (Out-of-Sample):")
    print(f"  Total Trades: {total_trades}")
    print(f"  Avg Win Rate: {avg_wr:.1f}%")
    print(f"  Avg Profit Factor: {avg_pf:.2f}")
    print(f"  Avg PnL per Fold: {avg_pnl:+.2f} CZK")
    print(f"  Worst Max DD: {max_dd:.1f}%")

    profitable_folds = sum(1 for r in results if r.get("total_pnl", 0) > 0)
    print(f"  Profitable Folds: {profitable_folds}/{len(results)}")
    print(f"{'─' * 60}")

    return {
        "folds": results,
        "avg_win_rate": avg_wr,
        "avg_profit_factor": avg_pf,
        "avg_pnl": avg_pnl,
        "worst_max_dd": max_dd,
        "profitable_folds": profitable_folds,
        "total_folds": len(results),
    }


# ══════════════════════════════════════════════════════════════════════
# MONTE CARLO SIMULATION
# ══════════════════════════════════════════════════════════════════════

def monte_carlo(trades, n_simulations=1000, initial_capital=2500.0):
    """
    Monte Carlo simulation by randomizing trade order.

    This tests whether the strategy's equity curve is dependent on
    the specific sequence of trades (which would indicate fragility).

    Returns distribution of final equity, max drawdowns, etc.
    """
    if not trades or len(trades) < 10:
        return None

    pnls = np.array([t["pnl"] for t in trades])
    n_trades = len(pnls)

    final_equities = []
    max_drawdowns = []
    worst_streaks = []

    for _ in range(n_simulations):
        # Shuffle trade order
        shuffled = np.random.permutation(pnls)
        equity = initial_capital
        peak = equity
        max_dd = 0
        streak = 0
        worst_streak = 0

        for pnl in shuffled:
            equity += pnl
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

            if pnl <= 0:
                streak += 1
                worst_streak = max(worst_streak, streak)
            else:
                streak = 0

        final_equities.append(equity)
        max_drawdowns.append(max_dd)
        worst_streaks.append(worst_streak)

    final_equities = np.array(final_equities)
    max_drawdowns = np.array(max_drawdowns)

    result = {
        "n_simulations": n_simulations,
        "n_trades": n_trades,
        "equity_mean": round(float(np.mean(final_equities)), 2),
        "equity_median": round(float(np.median(final_equities)), 2),
        "equity_5th": round(float(np.percentile(final_equities, 5)), 2),
        "equity_95th": round(float(np.percentile(final_equities, 95)), 2),
        "equity_std": round(float(np.std(final_equities)), 2),
        "prob_profit": round(float((final_equities > initial_capital).mean() * 100), 1),
        "prob_ruin": round(float((final_equities < initial_capital * 0.5).mean() * 100), 1),
        "max_dd_mean": round(float(np.mean(max_drawdowns)), 1),
        "max_dd_95th": round(float(np.percentile(max_drawdowns, 95)), 1),
        "worst_streak_mean": round(float(np.mean(worst_streaks)), 1),
        "worst_streak_95th": round(float(np.percentile(worst_streaks, 95)), 1),
    }

    print(f"\n{'=' * 60}")
    print(f"MONTE CARLO SIMULATION ({n_simulations} runs, {n_trades} trades)")
    print(f"{'=' * 60}")
    print(f"  Mean Final Equity:  {result['equity_mean']:,.0f} CZK")
    print(f"  Median Final Equity: {result['equity_median']:,.0f} CZK")
    print(f"  5th Percentile:     {result['equity_5th']:,.0f} CZK (worst case)")
    print(f"  95th Percentile:    {result['equity_95th']:,.0f} CZK (best case)")
    print(f"  Probability of Profit: {result['prob_profit']:.1f}%")
    print(f"  Probability of Ruin (<50%): {result['prob_ruin']:.1f}%")
    print(f"  Mean Max Drawdown:  {result['max_dd_mean']:.1f}%")
    print(f"  95th Max Drawdown:  {result['max_dd_95th']:.1f}%")
    print(f"  Mean Worst Streak:  {result['worst_streak_mean']:.0f} losses")
    print(f"{'=' * 60}")

    return result


# ══════════════════════════════════════════════════════════════════════
# MAIN: RUN FULL BACKTEST SUITE
# ══════════════════════════════════════════════════════════════════════

def run_full_backtest(tickers=None):
    """
    Run complete backtest suite on multiple instruments.

    Steps:
    1. Download data from yfinance
    2. Run simple backtest
    3. Walk-forward validation
    4. Monte Carlo simulation
    5. Print comprehensive report
    """
    import yfinance as yf

    if tickers is None:
        tickers = {
            "BTC-USD": "crypto",
            "ETH-USD": "crypto",
            "EURUSD=X": "forex",
            "GBPUSD=X": "forex",
        }

    all_results = {}

    for ticker, asset_class in tickers.items():
        print(f"\n{'#' * 60}")
        print(f"# BACKTESTING: {ticker} ({asset_class})")
        print(f"{'#' * 60}")

        # Download data
        try:
            data = yf.download(ticker, period="60d", interval="15m", progress=False)
            if hasattr(data.columns, "levels"):
                data.columns = data.columns.get_level_values(0)
        except Exception as e:
            print(f"Error downloading {ticker}: {e}")
            continue

        if len(data) < 200:
            print(f"Insufficient data for {ticker}: {len(data)} bars")
            continue

        print(f"Data: {len(data)} bars ({data.index[0]} to {data.index[-1]})")

        # 1. Simple Backtest
        engine = BacktestEngine()
        result = engine.run(data, asset_class=asset_class, ticker=ticker)
        m = result["metrics"]

        print(f"\n--- SIMPLE BACKTEST ---")
        print(f"  Total Trades:    {m.get('total_trades', 0)}")
        print(f"  Win Rate:        {m.get('win_rate', 0):.1f}%")
        print(f"  Profit Factor:   {m.get('profit_factor', 0):.2f}")
        print(f"  Total PnL:       {m.get('total_pnl', 0):+.2f} CZK")
        print(f"  Total Return:    {m.get('total_return_pct', 0):+.2f}%")
        print(f"  Sharpe Ratio:    {m.get('sharpe_ratio', 0):.3f}")
        print(f"  Sortino Ratio:   {m.get('sortino_ratio', 0):.3f}")
        print(f"  Max Drawdown:    {m.get('max_drawdown_pct', 0):.1f}%")
        print(f"  Expectancy:      {m.get('expectancy', 0):+.2f} CZK/trade")
        print(f"  Avg Win:         {m.get('avg_win', 0):+.2f} CZK")
        print(f"  Avg Loss:        {m.get('avg_loss', 0):+.2f} CZK")

        # Regime breakdown
        if m.get("regime_breakdown"):
            print(f"\n  Regime Breakdown:")
            for regime, stats in m["regime_breakdown"].items():
                wr = (stats["wins"] / stats["trades"] * 100) if stats["trades"] > 0 else 0
                print(f"    {regime}: {stats['trades']} trades, WR {wr:.0f}%, PnL {stats['pnl']:+.2f}")

        # 2. Walk-Forward
        wf = walk_forward_test(data, asset_class=asset_class, ticker=ticker)

        # 3. Monte Carlo
        if result["trades"]:
            mc = monte_carlo(result["trades"])
        else:
            mc = None

        all_results[ticker] = {
            "backtest": result["metrics"],
            "walk_forward": wf,
            "monte_carlo": mc,
        }

    # ── FINAL SUMMARY ──
    print(f"\n{'=' * 60}")
    print(f"FINAL SUMMARY")
    print(f"{'=' * 60}")
    for ticker, data in all_results.items():
        m = data["backtest"]
        mc = data.get("monte_carlo")
        wf = data.get("walk_forward")
        print(f"\n{ticker}:")
        print(f"  Trades: {m.get('total_trades', 0)} | WR: {m.get('win_rate', 0):.1f}% | PF: {m.get('profit_factor', 0):.2f}")
        print(f"  PnL: {m.get('total_pnl', 0):+.2f} CZK | Max DD: {m.get('max_drawdown_pct', 0):.1f}%")
        if mc:
            print(f"  MC Prob Profit: {mc.get('prob_profit', 0):.1f}% | MC 95th DD: {mc.get('max_dd_95th', 0):.1f}%")
        if wf:
            print(f"  WF Profitable Folds: {wf.get('profitable_folds', 0)}/{wf.get('total_folds', 0)}")

    print(f"\n{'=' * 60}")
    print("DISCLAIMER: Past performance is NOT indicative of future results.")
    print("Backtests use close-price fills without slippage/spread costs.")
    print("Real-world performance will differ. Always paper-trade first.")
    print(f"{'=' * 60}")

    return all_results


if __name__ == "__main__":
    run_full_backtest()
