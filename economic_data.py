import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, date
import yfinance as yf
import io

def get_economic_calendar():
    """
    Fetches REAL economic calendar data from ForexFactory public verified feed.
    Fallback to Yahoo Finance News if feed is unavailable.
    """
    # 1. Try ForexFactory Public Feed (Real Data)
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            events = []
            
            today_str = date.today().strftime("%Y-%m-%d")
            
            for child in root:
                # Format: <event><title>...</title><country>USD</country><date>...</date><time>...</time><impact>...</impact></event>
                event_date = child.find('date').text
                
                # Filter for today only to keep dashboard clean
                if event_date == today_str:
                    impact = child.find('impact').text  # Low, Medium, High
                    events.append({
                        "Time": child.find('time').text,
                        "Country": child.find('country').text,
                        "Event": child.find('title').text,
                        "Impact": impact,
                        "Forecast": child.find('forecast').text if child.find('forecast') is not None else "",
                        "Previous": child.find('previous').text if child.find('previous') is not None else ""
                    })
            
            if events:
                df = pd.DataFrame(events)
                return df
                
    except Exception as e:
        print(f"Calendar feed error: {e}")

    # 2. Fallback: Yahoo Finance News (Real News) - if Calendar fails
    # This ensures we always show REAL data, never mock data.
    try:
        news_data = []
        tickers = ["^GSPC", "EURUSD=X", "^VIX"] # S&P500, Forex, VIX
        
        for t in tickers:
            ticker = yf.Ticker(t)
            news = ticker.news
            if news:
                for n in news[:2]: # Top 2 per ticker
                    pub_time = datetime.fromtimestamp(n.get('providerPublishTime', 0)).strftime('%H:%M')
                    news_data.append({
                        "Time": pub_time,
                        "Country": "Global",
                        "Event": n.get('title', 'N/A'),
                        "Impact": "Medium", # Assume news is medium impact
                        "Source": n.get('publisher', 'Yahoo')
                    })
        
        if news_data:
            return pd.DataFrame(news_data)

    except Exception as e:
        print(f"News fetch error: {e}")

    return pd.DataFrame() # Return empty if everything fails, better than fake data

def is_market_volatile_today():
    """
    Checks real VIX (Volatility Index) data.
    """
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="2d")
        if len(hist) >= 1:
            curr_close = hist['Close'].iloc[-1]
            return curr_close > 25, f"VIX: {curr_close:.2f}"
    except:
        pass
    return False, "VIX Unavailable"
