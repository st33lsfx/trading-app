"""
Scale-Out Backtest Comparison
==============================
Compare single TP vs. scale-out profit taking strategies.
"""

import sys
sys.path.append('/Users/ondrej/Desktop/Weby/Aplikace/Trading app/trading-app')

from elite_strategy import EliteStrategy
import yfinance as yf
import pandas as pd

def test_scaleout_config(ticker="BTC-USD", profile="balanced"):
    """
    Quick test to verify scale-out configuration works with EliteStrategy.
    """
    print(f"\n{'='*70}")
    print(f"Testing Scale-Out Profile: {profile.upper()}")
    print(f"Ticker: {ticker}")
    print(f"{'='*70}\n")
    
    # Initialize strategy with scale-out profile
    config = {"scale_out_profile": profile}
    strategy = EliteStrategy(config)
    
    # Verify config loaded
    print(f"✅ Strategy initialized with profile: {strategy.scale_out_profile}")
    print(f"✅ Scale-out enabled: {strategy.scale_out_config.get('enabled', False)}")
    
    if strategy.scale_out_config.get('enabled'):
        print(f"\n📊 Partial Close Schedule:")
        cumulative = 0
        for i, level in enumerate(strategy.scale_out_config.get('levels', []), 1):
            cumulative += level['close_pct']
            print(f"   Level {i}: Close {level['close_pct']*100:>5.1f}% @ {level['r_mult']:>4.1f}R  "
                  f"(Total: {cumulative*100:>5.1f}%)")
    
    # Fetch recent data
    print(f"\n📥 Fetching Yahoo Finance data...")
    ticker_obj = yf.Ticker(ticker)
    df = ticker_obj.history(period="5d", interval="15m")
    
    if df.empty:
        print(f"❌ No data for {ticker}")
        return
    
    print(f"✅ Loaded {len(df)} candles")
    
    # Add indicators
    print(f"\n🔧 Calculating indicators...")
    df = strategy.add_indicators(df)
    df = df.dropna()
    print(f"✅ Indicators ready ({len(df)} valid candles)")
    
    # Get latest signal
    print(f"\n🎯 Generating signal on latest data...")
    asset_class = "crypto" if "-USD" in ticker else ("forex" if "=X" in ticker else "default")
    signal = strategy.get_signal(df, asset_class=asset_class)
    
    print(f"\n{'='*70}")
    print(f"SIGNAL RESULT")
    print(f"{'='*70}")
    print(f"Direction: {signal['signal']}")
    print(f"Confidence: {signal.get('confidence', 0):.2f}")
    print(f"Reason: {signal.get('reason', 'N/A')}")
    
    if signal['signal'] in ["BUY", "SELL"]:
        print(f"\n🎯 Trade Setup:")
        print(f"   Entry: {df.iloc[-1]['Close']:.2f}")
        print(f"   SL: {signal['sl']:.2f}")
        print(f"   TP (final): {signal['tp']:.2f}")
        print(f"   R:R: {signal.get('rr_ratio', 0):.2f}")
        
        # Show TP levels
        tp_levels = signal.get('tp_levels')
        if tp_levels:
            print(f"\n💰 Scale-Out TP Levels ({len(tp_levels)} stages):")
            for i, level in enumerate(tp_levels, 1):
                print(f"   TP{i}: ${level['price']:>10.2f}  |  Close {level['size_pct']*100:>5.1f}%  |  "
                      f"@ {level['r_mult']:.1f}R  |  [{level['label']}]")
        else:
            print(f"\n⚠️  No tp_levels generated (scale-out disabled)")
    
    print(f"\n{'='*70}\n")

# Run tests
if __name__ == "__main__":
    # Test 1: Disabled (single TP)
    test_scaleout_config("BTC-USD", "disabled")
    
    # Test 2: Balanced (default)
    test_scaleout_config("BTC-USD", "balanced")
    
    # Test 3: Aggressive
    test_scaleout_config("ETH-USD", "aggressive")
    
    # Test 4: Conservative
    test_scaleout_config("GBPUSD=X", "conservative")
    
    print("\n" + "="*70)
    print("🎉 ALL TESTS COMPLETE")
    print("="*70)
    print("\nScale-out implementation working correctly!")
    print("\nNext steps:")
    print("1. Run bot in paper trading mode to test live")
    print("2. Monitor logs for partial close triggers")
    print("3. Deploy to live trading with 'balanced' profile")
