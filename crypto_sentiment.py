"""
Crypto Sentiment Module — Pro Trading Data Sources
==================================================
- Fear & Greed Index (Alternative.me)
- Funding Rate (Binance Futures)
Používá se jako filtr před vstupem do obchodu.
"""

import requests
import time
from typing import Tuple, Optional

# Cache 1 hodina
CACHE_TTL = 3600


class CryptoSentiment:
    def __init__(self):
        self._fng_cache = None
        self._fng_cache_time = 0
        self._funding_cache = {}  # symbol -> (rate, timestamp)
        self._funding_cache_time = 0

    def get_fear_greed(self) -> Tuple[Optional[int], Optional[str]]:
        """
        Fear & Greed Index 0-100.
        Returns: (value, classification) or (None, None) on error.
        """
        now = time.time()
        if self._fng_cache is not None and (now - self._fng_cache_time) < CACHE_TTL:
            return self._fng_cache

        try:
            r = requests.get(
                "https://api.alternative.me/fng/?limit=1",
                timeout=5,
                headers={"User-Agent": "TradingBot/1.0"}
            )
            if r.status_code == 200:
                data = r.json()
                items = data.get("data", [])
                if items:
                    val = int(items[0].get("value", 0))
                    cls = items[0].get("value_classification", "Unknown")
                    self._fng_cache = (val, cls)
                    self._fng_cache_time = now
                    return (val, cls)
        except Exception:
            pass
        return (None, None)

    def get_funding_rate(self, symbol: str = "BTCUSDT") -> Optional[float]:
        """
        Binance Futures funding rate (8h periodic).
        Positive = longs pay shorts. High > 0.01 = crowded long.
        Returns: rate as decimal (e.g. 0.0001) or None.
        """
        now = time.time()
        if symbol in self._funding_cache:
            rate, ts = self._funding_cache[symbol]
            if now - ts < CACHE_TTL:
                return rate

        try:
            r = requests.get(
                f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit=1",
                timeout=5,
                headers={"User-Agent": "TradingBot/1.0"}
            )
            if r.status_code == 200:
                data = r.json()
                if data:
                    rate = float(data[0].get("fundingRate", 0))
                    self._funding_cache[symbol] = (rate, now)
                    return rate
        except Exception:
            pass
        return None

    def should_skip_crypto_trade(self, epic: str) -> Tuple[bool, str]:
        """
        Pro filter: skip obchod při extrémním sentimentu.
        Returns: (skip: bool, reason: str)
        """
        # 1. Fear & Greed
        val, cls = self.get_fear_greed()
        if val is not None:
            if val <= 20:  # Extreme Fear
                return True, f"Extreme Fear ({val}) — čekat na stabilitu"
            if val >= 80:  # Extreme Greed
                return True, f"Extreme Greed ({val}) — riziko korekce"

        # 2. Funding rate (jen pro BTC/ETH — mapování)
        symbol_map = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT"}
        binance_sym = symbol_map.get(epic.upper())
        if not binance_sym:
            binance_sym = "BTCUSDT"  # Default proxy pro altcoiny

        rate = self.get_funding_rate(binance_sym)
        if rate is not None:
            # Extrémní funding: > 0.05% = crowded (pro traders často 0.01–0.03%)
            if rate > 0.0005:
                return True, f"Funding {rate*100:.3f}% — overcrowded long"
            if rate < -0.0005:
                return True, f"Funding {rate*100:.3f}% — overcrowded short"

        return False, ""


# Singleton
_sentiment = None


def get_crypto_sentiment() -> CryptoSentiment:
    global _sentiment
    if _sentiment is None:
        _sentiment = CryptoSentiment()
    return _sentiment
