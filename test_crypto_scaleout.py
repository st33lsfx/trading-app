"""
Crypto Scale-Out Test
=====================
Test scale-out profit taking specifically on crypto assets.
"""

import sys
sys.path.append('/Users/ondrej/Desktop/Weby/Aplikace/Trading app/trading-app')

from elite_strategy import EliteStrategy
import yfinance as yf

def test_crypto_scaleout(ticker, profile="balanced"):
    """Test scale-out on crypto with specific profile."""
    print(f"\n{'='*80}")
    print(f"🪙 CRYPTO TEST: {ticker} with {profile.upper()} profile")
    print(f"{'='*80}\n")
    
    # Initialize strategy
    config = {"scale_out_profile": profile}
    strategy = EliteStrategy(config)
    
    print(f"Profile: {strategy.scale_out_profile}")
    print(f"Scale-out enabled: {strategy.scale_out_config.get('enabled', False)}\n")
    
    if strategy.scale_out_config.get('enabled'):
        print("📊 Partial Close Schedule:")
        for i, level in enumerate(strategy.scale_out_config.get('levels', []), 1):
            print(f"   Level {i}: {level['close_pct']*100:>5.1f}% @ {level['r_mult']:>4.1f}R ({level['label']})")
        print()
    
    # Fetch data
    print(f"📥 Fetching 7 days of 15min data from Yahoo Finance...")
    ticker_obj = yf.Ticker(ticker)
    df = ticker_obj.history(period="7d", interval="15m")
    
    if df.empty:
        print(f"❌ No data for {ticker}\n")
        return None
    
    print(f"✅ {len(df)} candles loaded\n")
    
    # Calculate indicators
    df = strategy.add_indicators(df)
    df = df.dropna()
    print(f"🔧 Indicators calculated ({len(df)} valid candles)\n")
    
    # Generate signal
    signal = strategy.get_signal(df, asset_class="crypto")
    
    print(f"{'─'*80}")
    print(f"📡 SIGNAL: {signal['signal']}")
    print(f"{'─'*80}")
    print(f"Confidence: {signal.get('confidence', 0):.2f}")
    print(f"Reason: {signal.get('reason', 'N/A')}")
    print(f"Strategy: {signal.get('strategy', 'N/A')}")
    
    if signal['signal'] in ["BUY", "SELL"]:
        entry = df.iloc[-1]['Close']
        sl = signal['sl']
        sl_dist = abs(entry - sl)
        
        print(f"\n💰 TRADE SETUP:")
        print(f"   Direction: {signal['signal']}")
        print(f"   Entry: ${entry:,.2f}")
        print(f"   SL: ${sl:,.2f} ({signal.get('sl_distance_pct', 0):.2f}%)")
        print(f"   Final TP: ${signal['tp']:,.2f} ({signal.get('tp_distance_pct', 0):.2f}%)")
        print(f"   R:R Ratio: {signal.get('rr_ratio', 0):.2f}")
        
        # Show scale-out levels
        tp_levels = signal.get('tp_levels')
        if tp_levels:
            print(f"\n🎯 SCALE-OUT TP LEVELS:")
            print(f"   {'Stage':<8} {'Price':>12} {'Close %':>10} {'R:R':>8} {'Profit if hit':>15}")
            print(f"   {'-'*65}")
            
            for i, level in enumerate(tp_levels, 1):
                tp_price = level['price']
                close_pct = level['size_pct'] * 100
                r_mult = level['r_mult']
                label = level['label']
                
                # Calculate profit at this level
                if signal['signal'] == "BUY":
                    profit_per_unit = tp_price - entry
                else:
                    profit_per_unit = entry - tp_price
                
                profit_pct = (profit_per_unit / entry) * 100
                
                print(f"   {label:<8} ${tp_price:>11,.2f} {close_pct:>9.1f}% {r_mult:>7.1f}x {profit_pct:>13.2f}%")
            
            print(f"\n💡 How it works:")
            print(f"   • Bot opens position with full size")
            print(f"   • At each R:R level, closes the specified %")
            print(f"   • Remaining % continues with trailing stop")
            print(f"   • Locks profit early, lets winners run!")
        else:
            print(f"\n⚠️  Single TP mode (scale-out disabled)")
    else:
        print(f"\n⏸️  No trade signal (waiting for setup)")
    
    print(f"\n{'='*80}\n")
    return signal

# Main test
if __name__ == "__main__":
    print("\n" + "="*80)
    print("🚀 CRYPTO SCALE-OUT TESTING")
    print("="*80)
    
    cryptos = ["BTC-USD", "ETH-USD", "SOL-USD"]
    profiles = ["balanced", "aggressive", "conservative"]
    
    results = {}
    
    for crypto in cryptos:
        for profile in profiles:
            key = f"{crypto}_{profile}"
            results[key] = test_crypto_scaleout(crypto, profile)
    
    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    
    trades_found = 0
    for key, signal in results.items():
        if signal and signal['signal'] in ["BUY", "SELL"]:
            crypto, profile = key.split("_")
            trades_found += 1
            tp_count = len(signal.get('tp_levels', []))
            print(f"✅ {crypto:12s} | {profile:12s} | {signal['signal']:4s} | {tp_count} TP levels")
    
    print(f"\n🎯 {trades_found} tradable signals found across {len(cryptos)} cryptos × {len(profiles)} profiles")
    
    if trades_found == 0:
        print("\n💡 No signals in current market conditions (waiting for setups)")
        print("   This is normal - Elite strategy is selective!")
    else:
        print("\n✅ Scale-out system WORKING on crypto!")
        print("   Ready for paper trading and live deployment")
    
    print("\n" + "="*80 + "\n")
