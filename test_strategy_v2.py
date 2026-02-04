"""
Test Mean Reversion Strategy v2.0
=================================
Rychlý backtest nové strategie s vylepšenými filtry.
"""

import yfinance as yf
import pandas as pd
from mean_reversion_strategy import MeanReversionStrategy

def run_backtest(ticker, period="1mo", interval="1h"):
    """Jednoduchý backtest mean reversion strategie."""
    
    print(f"\n{'='*60}")
    print(f"BACKTEST: {ticker}")
    print(f"Period: {period}, Interval: {interval}")
    print(f"{'='*60}")
    
    # Fetch data
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    if df.empty or len(df) < 100:
        print(f"❌ Not enough data for {ticker}")
        return None
    
    # Initialize strategy - optimalizované parametry
    strategy = MeanReversionStrategy({
        "rsi_oversold": 38,
        "rsi_overbought": 62,
        "atr_sl_mult": 2.0,       # Širší SL
        "min_rr_ratio": 1.2,      # Realistické R:R
        "use_trend_filter": False,  # Mean reversion jde proti trendu
        "use_volatility_filter": True,
        "use_volume_filter": False,
        "use_session_filter": False,
    })
    
    # Simulate trades
    trades = []
    position = None
    
    for i in range(60, len(df)):
        df_slice = df.iloc[:i+1].copy()
        result = strategy.get_signal(df_slice)
        
        current_price = df.iloc[i]['Close']
        current_time = df.index[i]
        
        # Check exit if in position
        if position:
            high = df.iloc[i]['High']
            low = df.iloc[i]['Low']
            
            if position['direction'] == 'BUY':
                # Check SL
                if low <= position['sl']:
                    pnl_pct = ((position['sl'] - position['entry']) / position['entry']) * 100
                    trades.append({
                        'direction': 'BUY',
                        'entry': position['entry'],
                        'exit': position['sl'],
                        'pnl_pct': pnl_pct,
                        'exit_reason': 'SL',
                        'entry_time': position['time'],
                        'exit_time': current_time
                    })
                    position = None
                    continue
                # Check TP
                elif high >= position['tp']:
                    pnl_pct = ((position['tp'] - position['entry']) / position['entry']) * 100
                    trades.append({
                        'direction': 'BUY',
                        'entry': position['entry'],
                        'exit': position['tp'],
                        'pnl_pct': pnl_pct,
                        'exit_reason': 'TP',
                        'entry_time': position['time'],
                        'exit_time': current_time
                    })
                    position = None
                    continue
                    
            elif position['direction'] == 'SELL':
                # Check SL
                if high >= position['sl']:
                    pnl_pct = ((position['entry'] - position['sl']) / position['entry']) * 100
                    trades.append({
                        'direction': 'SELL',
                        'entry': position['entry'],
                        'exit': position['sl'],
                        'pnl_pct': pnl_pct,
                        'exit_reason': 'SL',
                        'entry_time': position['time'],
                        'exit_time': current_time
                    })
                    position = None
                    continue
                # Check TP
                elif low <= position['tp']:
                    pnl_pct = ((position['entry'] - position['tp']) / position['entry']) * 100
                    trades.append({
                        'direction': 'SELL',
                        'entry': position['entry'],
                        'exit': position['tp'],
                        'pnl_pct': pnl_pct,
                        'exit_reason': 'TP',
                        'entry_time': position['time'],
                        'exit_time': current_time
                    })
                    position = None
                    continue
        
        # Check for new entry if no position
        if position is None:
            signal = result.get('signal')
            confidence = result.get('confidence', 0)
            
            if signal in ['BUY', 'SELL'] and confidence >= 0.6:
                sl = result.get('sl')
                tp = result.get('tp')
                
                if sl and tp:
                    position = {
                        'direction': signal,
                        'entry': current_price,
                        'sl': sl,
                        'tp': tp,
                        'time': current_time
                    }
    
    # Calculate metrics
    if not trades:
        print("❌ No trades generated")
        return None
    
    total = len(trades)
    wins = len([t for t in trades if t['pnl_pct'] > 0])
    losses = total - wins
    
    win_rate = (wins / total) * 100
    
    gross_profit = sum([t['pnl_pct'] for t in trades if t['pnl_pct'] > 0])
    gross_loss = abs(sum([t['pnl_pct'] for t in trades if t['pnl_pct'] < 0]))
    
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999
    total_return = sum([t['pnl_pct'] for t in trades])
    
    avg_win = gross_profit / wins if wins > 0 else 0
    avg_loss = gross_loss / losses if losses > 0 else 0
    
    # Print results
    print(f"\n📊 RESULTS:")
    print(f"   Total Trades: {total}")
    print(f"   Wins: {wins} | Losses: {losses}")
    print(f"   Win Rate: {win_rate:.1f}%")
    print(f"   Profit Factor: {profit_factor:.2f}")
    print(f"   Total Return: {total_return:.2f}%")
    print(f"   Avg Win: +{avg_win:.2f}% | Avg Loss: -{avg_loss:.2f}%")
    
    # Exit reasons
    tp_exits = len([t for t in trades if t['exit_reason'] == 'TP'])
    sl_exits = len([t for t in trades if t['exit_reason'] == 'SL'])
    print(f"\n   Exit Reasons: TP={tp_exits}, SL={sl_exits}")
    
    # Direction breakdown
    longs = [t for t in trades if t['direction'] == 'BUY']
    shorts = [t for t in trades if t['direction'] == 'SELL']
    long_wins = len([t for t in longs if t['pnl_pct'] > 0])
    short_wins = len([t for t in shorts if t['pnl_pct'] > 0])
    
    print(f"\n   LONG: {len(longs)} trades ({long_wins} wins = {long_wins/len(longs)*100 if longs else 0:.0f}%)")
    print(f"   SHORT: {len(shorts)} trades ({short_wins} wins = {short_wins/len(shorts)*100 if shorts else 0:.0f}%)")
    
    # Sample trades
    print(f"\n   Last 5 trades:")
    for t in trades[-5:]:
        emoji = "✅" if t['pnl_pct'] > 0 else "❌"
        print(f"   {emoji} {t['direction']}: {t['pnl_pct']:+.2f}% ({t['exit_reason']})")
    
    return {
        'ticker': ticker,
        'total_trades': total,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'total_return': total_return,
        'trades': trades
    }


def main():
    """Test na více tickerech."""
    
    print("=" * 60)
    print("🧪 MEAN REVERSION STRATEGY v2.0 - BACKTEST")
    print("=" * 60)
    
    # Tickers to test (same as in bot)
    tickers = [
        ("ETH-USD", "Ethereum"),
        ("GBPUSD=X", "GBP/USD"),
        ("AUDUSD=X", "AUD/USD"),
        ("NZDUSD=X", "NZD/USD"),
        ("AMD", "AMD"),
    ]
    
    results = []
    
    for ticker, name in tickers:
        result = run_backtest(ticker, period="2mo", interval="1h")
        if result:
            results.append(result)
    
    # Summary
    if results:
        print("\n" + "=" * 60)
        print("📈 SUMMARY")
        print("=" * 60)
        
        total_trades = sum(r['total_trades'] for r in results)
        avg_wr = sum(r['win_rate'] for r in results) / len(results)
        avg_pf = sum(r['profit_factor'] for r in results) / len(results)
        total_ret = sum(r['total_return'] for r in results)
        
        print(f"\n   Tickers tested: {len(results)}")
        print(f"   Total trades: {total_trades}")
        print(f"   Average Win Rate: {avg_wr:.1f}%")
        print(f"   Average Profit Factor: {avg_pf:.2f}")
        print(f"   Combined Return: {total_ret:.2f}%")
        
        print("\n   Per ticker:")
        for r in sorted(results, key=lambda x: x['profit_factor'], reverse=True):
            emoji = "🟢" if r['profit_factor'] > 1 else "🔴"
            print(f"   {emoji} {r['ticker']}: PF={r['profit_factor']:.2f}, WR={r['win_rate']:.0f}%, Ret={r['total_return']:.1f}%")


if __name__ == "__main__":
    main()
