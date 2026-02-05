"""
Hybrid Strategy Backtester
===========================
Testuje HybridStrategy na historických datech s realistickou simulací trades.
"""
import yfinance as yf
import warnings
from hybrid_strategy import HybridStrategy
from learning_engine import get_learning_engine
warnings.filterwarnings('ignore')


def backtest_ticker(ticker, period='30d', interval='5m', verbose=False):
    """
    Backtest HybridStrategy na jednom tickeru.
    
    Returns:
        dict s výsledky nebo None
    """
    data = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    
    if len(data) < 100:
        return None
    
    # Flatten columns if multi-index
    if hasattr(data.columns, 'levels'):
        data.columns = data.columns.get_level_values(0)
    
    # Load learned params
    le = get_learning_engine()
    learned_params = le.get_learned_params()
    
    # Apply params
    config = {}
    if learned_params:
         config.update(learned_params)
         # Ensure strategy keys match
         if "rsi_oversold" in learned_params: config["rsi_oversold"] = learned_params["rsi_oversold"]
         if "rsi_overbought" in learned_params: config["rsi_overbought"] = learned_params["rsi_overbought"]
    
    strategy = HybridStrategy(config)
    
    trades = []
    position = None
    
    # Walk-forward: start from bar 100, check every 10 bars for speed
    for i in range(100, len(data) - 10, 10):
        df_slice = data.iloc[:i+1].copy()
        
        try:
            result = strategy.get_signal(df_slice)
            signal = result.get('signal', 'NEUTRAL')
            regime = result.get('regime', 'UNKNOWN')
            sl = result.get('sl')
            tp = result.get('tp')
        except:
            continue
        
        current_price = float(data.iloc[i]['Close'])
        
        # Check existing position
        if position:
            # Check SL/TP hit
            high = float(data.iloc[i]['High'])
            low = float(data.iloc[i]['Low'])
            
            if position['direction'] == 'BUY':
                if low <= position['sl']:
                    # SL hit
                    pnl = (position['sl'] - position['entry']) / position['entry'] * 100
                    trades.append({'pnl': pnl, 'win': False, 'regime': position['regime']})
                    position = None
                elif high >= position['tp']:
                    # TP hit
                    pnl = (position['tp'] - position['entry']) / position['entry'] * 100
                    trades.append({'pnl': pnl, 'win': True, 'regime': position['regime']})
                    position = None
            else:  # SELL
                if high >= position['sl']:
                    # SL hit
                    pnl = (position['entry'] - position['sl']) / position['entry'] * 100
                    trades.append({'pnl': pnl, 'win': False, 'regime': position['regime']})
                    position = None
                elif low <= position['tp']:
                    # TP hit
                    pnl = (position['entry'] - position['tp']) / position['entry'] * 100
                    trades.append({'pnl': pnl, 'win': True, 'regime': position['regime']})
                    position = None
            
            # Timeout after 50 bars
            if position and (i - position['bar']) > 50:
                pnl = (current_price - position['entry']) / position['entry'] * 100
                if position['direction'] == 'SELL':
                    pnl = -pnl
                trades.append({'pnl': pnl, 'win': pnl > 0, 'regime': position['regime']})
                position = None
        
        # Open new position
        if position is None and signal in ['BUY', 'SELL'] and sl and tp:
            position = {
                'direction': signal,
                'entry': current_price,
                'sl': sl,
                'tp': tp,
                'bar': i,
                'regime': regime
            }
            if verbose:
                print(f"  {signal} @ {current_price:.5f} SL:{sl:.5f} TP:{tp:.5f} ({regime})")
    
    if not trades:
        return None
    
    # Calculate stats
    wins = sum(1 for t in trades if t['win'])
    total = len(trades)
    total_pnl = sum(t['pnl'] for t in trades)
    
    gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else 999
    
    return {
        'ticker': ticker,
        'trades': total,
        'wins': wins,
        'wr': wins / total * 100 if total > 0 else 0,
        'pf': min(pf, 999),
        'ret': total_pnl
    }


def run_backtest(tickers=None, period='7d', interval='5m'):
    """
    Spusť backtest na seznamu tickerů.
    Default period zkrácena na 7 dní pro rychlost.
    """
    if tickers is None:
        tickers = [
            'AUDUSD=X', 'NZDUSD=X', 'GBPUSD=X', 'EURUSD=X',
            'BTC-USD', 'ETH-USD', 'CADJPY=X', 'NZDJPY=X'
        ]
    
    print('='*60)
    print(f'HYBRID STRATEGY BACKTEST ({period}, {interval})')
    print('='*60)
    
    results = []
    for ticker in tickers:
        r = backtest_ticker(ticker, period=period, interval=interval)
        if r and r['trades'] >= 3:
            results.append(r)
            icon = '✅' if r['pf'] >= 1.0 else '❌'
            print(f"{icon} {r['ticker']:10} {r['trades']:3}t WR {r['wr']:5.1f}% PF {r['pf']:5.2f} Ret {r['ret']:+7.2f}%")
    
    if results:
        total_trades = sum(r['trades'] for r in results)
        total_ret = sum(r['ret'] for r in results)
        avg_pf = sum(r['pf'] for r in results) / len(results)
        profitable = len([r for r in results if r['pf'] >= 1])
        
        print('-'*60)
        print(f'📊 Total: {total_trades} trades, Return: {total_ret:+.2f}%')
        print(f'✅ Profitable: {profitable}/{len(results)} ({100*profitable/len(results):.0f}%)')
        print(f'📈 Avg PF: {avg_pf:.2f}')
    else:
        print('No results with sufficient trades')
    
    print('='*60)
    return results


if __name__ == '__main__':
    run_backtest()
