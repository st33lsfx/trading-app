"""
USD/CZK Exchange Rate Auto-Updater
===================================
Call this at bot startup to get fresh exchange rate.
"""

import requests

def get_current_usd_czk_rate(fallback=20.4):
    """
    Fetch current USD/CZK exchange rate from API.
    
    Returns:
        float: Current exchange rate, or fallback value if API fails
    """
    try:
        response = requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=5
        )
        if response.status_code == 200:
            rate = response.json()['rates'].get('CZK', fallback)
            print(f"💱 USD/CZK rate fetched: {rate:.2f}")
            return round(rate, 2)
    except Exception as e:
        print(f"⚠️  Failed to fetch exchange rate: {e}")
    
    print(f"💱 Using fallback rate: {fallback}")
    return fallback

if __name__ == "__main__":
    rate = get_current_usd_czk_rate()
    print(f"\nCurrent USD/CZK: {rate}")
    print(f"\n2000 CZK = {2000/rate:.2f} USD")
