import datetime

def is_scalping_hours(utc_now=None):
    """
    Scalping works best in liquid hours (London/NY overlap, avoid Asian session for Forex).
    Returns True if we're in "good" scalping window (UTC).
    - 07:00–11:00 UTC: London
    - 13:30–17:00 UTC: NY open + overlap
    """
    now = utc_now or datetime.datetime.utcnow().time()
    london_start = datetime.time(7, 0)
    london_end = datetime.time(11, 0)
    ny_start = datetime.time(13, 30)
    ny_end = datetime.time(17, 0)
    if london_start <= now <= london_end:
        return True
    if ny_start <= now <= ny_end:
        return True
    return False


def is_market_open(exchange_data):
    """
    Checks if the exchange is currently open.
    Note: This is a simplified check assuming the bot runs in a timezone 
    compatible with the API's returned schedule or converting properly.
    T212 API returns times usually in local exchange time or UTC.
    The 'exchanges' endpoint returns 'workingSchedules'.
    
    Structure of exchange data from API (simplified expectation):
    {
        "id": 56,
        "name": "NASDAQ",
        "workingSchedules": [
            {"id": 1, "timeEvents": [{"type": "OPEN", "time": "09:30"}, ...]} 
            # Actually, per docs, it's complex.
        ]
    }
    
    FOR NOW (MVP): We will use a static approximation based on Current UTC time and known market hours 
    because parsing the full dynamic schedule is complex without the full JSON model.
    
    US: 14:30 - 21:00 UTC (approx)
    DE: 08:00 - 16:30 UTC
    UK: 08:00 - 16:30 UTC
    """
    now_utc = datetime.datetime.utcnow().time()
    
    # Simplified logic based on exchange names/regions
    name = exchange_data.get('name', '').upper()
    
    # Define time ranges (UTC)
    us_open = datetime.time(14, 30)
    us_close = datetime.time(21, 0)
    
    eu_open = datetime.time(8, 0)
    eu_close = datetime.time(16, 30) # Xetra closes 17:30 CET = 16:30 UTC approx
    
    if 'NASDAQ' in name or 'NYSE' in name or 'US' in name:
         return us_open <= now_utc <= us_close
         
    if 'DEUTSCH' in name or 'XETRA' in name or 'GERMANY' in name:
        return eu_open <= now_utc <= eu_close
        
    if 'LSE' in name or 'LONDON' in name or 'UK' in name:
        return eu_open <= now_utc <= eu_close

    # Default to assuming closed if unknown for safety, or open if you want to risk it.
    return False

def map_ticker_to_yf(t212_ticker):
    """
    Maps Trading 212 ticker to Yahoo Finance ticker.
    Examples:
    AAPL_US_EQ -> AAPL
    BMW_DE_EQ -> BMW.DE
    BARC_UK_EQ -> BARC.L
    """
    if "_US_EQ" in t212_ticker:
        return t212_ticker.replace("_US_EQ", "")
        
    if "_DE_EQ" in t212_ticker:
        base = t212_ticker.replace("_DE_EQ", "")
        return f"{base}.DE"
        
    if "_UK_EQ" in t212_ticker or "l_EQ" in t212_ticker: # UK often has 'l_EQ' e.g. TMGl_EQ or _UK_EQ
        # UK is tricky, often suffix .L 
        # T212: VOD_UK_EQ -> YF: VOD.L
        base = t212_ticker.split('_')[0]
        # Some tickers end with 'l' which might be part of the code or suffix
        if base.endswith('l'):
             base = base[:-1] # Remove 'l' suffix often seen in T212 for LSE
        return f"{base}.L"

    return None
