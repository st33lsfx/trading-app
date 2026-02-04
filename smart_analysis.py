# Smart Analysis Module
"""
Module for fetching external "smart" data:
- Analyst Ratings (Yahoo Finance)
- Market Sentiment (VIX, SPY)
"""

import yfinance as yf
import time

class SmartAnalyst:
    def __init__(self):
        self.cache = {}
        self.cache_expiry = 3600 * 4 # 4 hours cache for ratings
        self.market_sentiment_cache = {}
        
    def get_analyst_rating(self, yf_ticker):
        """
        Get analyst recommendation for a ticker.
        Returns: (rating_score, recommendation_key, target_price)
        Rating Score: 1.0 (Strong Buy) to -1.0 (Strong Sell)
        """
        # Check cache
        if yf_ticker in self.cache:
            data, timestamp = self.cache[yf_ticker]
            if time.time() - timestamp < self.cache_expiry:
                return data

        try:
            ticker = yf.Ticker(yf_ticker)
            info = ticker.info
            
            # Extract data
            rec_key = info.get('recommendationKey', 'none')
            target_mean = info.get('targetMeanPrice')
            current_price = info.get('currentPrice')
            
            # Scoring
            score = 0.0
            if rec_key in ['strong_buy', 'buy']:
                score = 1.0
            elif rec_key == 'hold':
                score = 0.0
            elif rec_key in ['sell', 'strong_sell', 'underperform']:
                score = -1.0
                
            # Upside check
            upside_pct = 0.0
            if target_mean and current_price:
                upside_pct = (target_mean - current_price) / current_price
            
            result = {
                "score": score,
                "recommendation": rec_key,
                "target_price": target_mean,
                "upside": upside_pct
            }
            
            # Save to cache
            self.cache[yf_ticker] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"⚠️ SmartAnalyst Error ({yf_ticker}): {e}")
            return {"score": 0.0, "recommendation": "neutral", "upside": 0}

    def get_market_sentiment(self):
        """
        Check global market sentiment using VIX and SPY.
        Returns: (is_safe, reason)
        """
        # Cache for 30 mins
        now = time.time()
        if 'vix' in self.market_sentiment_cache:
            data, ts = self.market_sentiment_cache['vix']
            if now - ts < 1800:
                return data

        try:
            # Check VIX (Fear Index)
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="1d")
            if hist.empty:
                return True, "No VIX data"
                
            current_vix = hist['Close'].iloc[-1]
            
            if current_vix > 30:
                result = (False, f"EXTREME FEAR (VIX {current_vix:.1f})")
            elif current_vix > 25:
                result = (False, f"High Volatility (VIX {current_vix:.1f})")
            else:
                result = (True, f"Market Calm (VIX {current_vix:.1f})")
                
            self.market_sentiment_cache['vix'] = (result, now)
            return result
            
        except Exception as e:
            print(f"⚠️ Market Sentiment Error: {e}")
            return True, "Error checking VIX"

# Singleton
_smart_analyst = None

def get_smart_analyst():
    global _smart_analyst
    if _smart_analyst is None:
        _smart_analyst = SmartAnalyst()
    return _smart_analyst
