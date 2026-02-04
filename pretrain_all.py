#!/usr/bin/env python3
"""
Pretrain Learning Engine - Backtest all 20 assets
"""
import json
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# All assets the bot scans
ASSETS = [
    # Forex
    "AUDNZD=X", "EURCHF=X", "NZDUSD=X", "CHFJPY=X", "EURAUD=X",
    "GBPCHF=X", "AUDCAD=X", "GBPAUD=X", "CADJPY=X", "NZDJPY=X",
    "GBPUSD=X", "USDCAD=X", "USDCHF=X", "EURGBP=X", "AUDUSD=X",
    "USDMXN=X", "USDTRY=X",
    # Stocks
    "AAPL", "GOOGL", "NVDA",
    # Crypto (bonus)
    "ETH-USD", "BTC-USD"
]

def add_indicators(df):
    """Add technical indicators for mean reversion strategy."""
    # Bollinger Bands (20 period)
    df['sma20'] = df['Close'].rolling(20).mean()
    df['std20'] = df['Close'].rolling(20).std()
    df['bb_upper'] = df['sma20'] + (2 * df['std20'])
    df['bb_lower'] = df['sma20'] - (2 * df['std20'])
    df['bb_mid'] = df['sma20']

    # RSI (14 period)
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # ATR (14 period)
    high_low = df['High'] - df['Low']
    high_close = abs(df['High'] - df['Close'].shift())
    low_close = abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    return df

def backtest_asset(ticker, period="3mo", interval="1h"):
    """Run backtest on single asset."""
    try:
        print(f"  Backtesting {ticker}...", end=" ", flush=True)

        # Download data
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if len(df) < 100:
            print("SKIP (insufficient data)")
            return None

        df = add_indicators(df)
        df = df.dropna()

        if len(df) < 60:
            print("SKIP (insufficient data after indicators)")
            return None

        # Strategy params (RSI 40/60 mean reversion)
        RSI_OVERSOLD = 40
        RSI_OVERBOUGHT = 60
        ATR_SL_MULT = 2.0

        trades = []
        position = None

        for i in range(60, len(df)):
            row = df.iloc[i]

            # Get scalar values
            low = float(row['Low'])
            high = float(row['High'])
            close = float(row['Close'])
            rsi = float(row['rsi'])
            bb_lower = float(row['bb_lower'])
            bb_upper = float(row['bb_upper'])
            bb_mid = float(row['bb_mid'])
            atr = float(row['atr'])

            # Check for exit if in position
            if position:
                # Check SL/TP hit
                if low <= position['sl']:
                    # Stop loss hit
                    pnl = position['sl'] - position['entry']
                    trades.append({
                        'pnl': pnl,
                        'pnl_pct': (pnl / position['entry']) * 100,
                        'win': False
                    })
                    position = None
                elif high >= position['tp']:
                    # Take profit hit
                    pnl = position['tp'] - position['entry']
                    trades.append({
                        'pnl': pnl,
                        'pnl_pct': (pnl / position['entry']) * 100,
                        'win': True
                    })
                    position = None
                continue  # Skip signal check if in position

            # Check for entry signal (mean reversion BUY)
            if low <= bb_lower and rsi < RSI_OVERSOLD:
                # BUY signal
                sl = close - (atr * ATR_SL_MULT)
                tp = bb_mid

                # Check R:R ratio
                risk = close - sl
                reward = tp - close
                if risk > 0 and (reward / risk) >= 1.0:
                    position = {
                        'entry': close,
                        'sl': sl,
                        'tp': tp
                    }

        # Calculate stats
        if not trades:
            print("SKIP (no trades)")
            return None

        wins = sum(1 for t in trades if t['win'])
        losses = len(trades) - wins
        total_pnl = sum(t['pnl_pct'] for t in trades)

        win_rate = (wins / len(trades)) * 100 if trades else 0

        gross_profit = sum(t['pnl_pct'] for t in trades if t['win'])
        gross_loss = abs(sum(t['pnl_pct'] for t in trades if not t['win']))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 2.0

        # Determine blacklist status
        auto_blacklisted = (
            len(trades) >= 5 and (
                win_rate < 35 or
                profit_factor < 0.7
            )
        )

        result = {
            "trades": len(trades),
            "wins": wins,
            "losses": losses,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "auto_blacklisted": bool(auto_blacklisted),  # Convert numpy bool
            "consecutive_losses": 0
        }

        status = "BLACKLIST" if auto_blacklisted else "OK"
        print(f"Trades: {len(trades)}, WR: {win_rate:.1f}%, PF: {profit_factor:.2f} [{status}]")

        return result

    except Exception as e:
        print(f"ERROR: {e}")
        return None

def main():
    print("=" * 60)
    print("PRETRAIN LEARNING ENGINE - All Assets Backtest")
    print("=" * 60)
    print(f"Strategy: Mean Reversion (RSI 40/60, BB touch)")
    print(f"Period: 3 months, Interval: 1h")
    print("=" * 60)

    ticker_stats = {}
    total_trades = 0
    total_wins = 0

    for ticker in ASSETS:
        result = backtest_asset(ticker)
        if result:
            ticker_stats[ticker] = result
            total_trades += result["trades"]
            total_wins += result["wins"]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    # Sort by profit factor
    sorted_tickers = sorted(
        ticker_stats.items(),
        key=lambda x: x[1]["profit_factor"],
        reverse=True
    )

    print("\nBEST PERFORMERS (not blacklisted):")
    for ticker, stats in sorted_tickers:
        if not stats["auto_blacklisted"]:
            print(f"  {ticker}: PF={stats['profit_factor']:.2f}, WR={stats['win_rate']:.1f}%")

    print("\nBLACKLISTED:")
    for ticker, stats in sorted_tickers:
        if stats["auto_blacklisted"]:
            print(f"  {ticker}: PF={stats['profit_factor']:.2f}, WR={stats['win_rate']:.1f}%")

    # Build learning data
    learning_data = {
        "ticker_stats": ticker_stats,
        "direction_stats": {
            "BUY": {
                "trades": total_trades,
                "wins": total_wins,
                "losses": total_trades - total_wins,
                "win_rate": round((total_wins / total_trades) * 100, 2) if total_trades > 0 else 0,
                "profit_factor": 1.5
            },
            "SELL": {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "profit_factor": 0
            }
        },
        "learned_params": {
            "rsi_oversold": 40,
            "rsi_overbought": 60,
            "atr_sl_mult": 2.0,
            "min_rr_ratio": 1.5,
            "enable_shorts": False
        },
        "last_updated": datetime.now().isoformat()
    }

    # Save to file
    with open("learning_data.json", "w") as f:
        json.dump(learning_data, f, indent=2)

    print(f"\n Saved to learning_data.json")
    print(f"Total: {len(ticker_stats)} assets, {total_trades} trades")

if __name__ == "__main__":
    main()
