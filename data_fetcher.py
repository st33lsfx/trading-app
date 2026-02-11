"""
Data fetcher — yfinance + Stooq fallback.
Když yfinance nevrátí data (blokace, rate limit, API změny), použije Stooq.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

# Mapování Yahoo ticker → Stooq ticker (lowercase, bez speciálních znaků)
STOOQ_TICKER_MAP = {
    "BTC-USD": "btcusd",
    "ETH-USD": "ethusd",
    "SOL-USD": "solusd",
    "BNB-USD": "bnbusd",
    "XRP-USD": "xrpusd",
    "ADA-USD": "adausd",
    "DOGE-USD": "dogeusd",
    "AVAX-USD": "avaxusd",
    "DOT-USD": "dotusd",
    "LINK-USD": "linkusd",
    "LTC-USD": "ltcusd",
    "EURUSD=X": "eurusd",
    "GBPUSD=X": "gbpusd",
    "USDJPY=X": "usdjpy",
    "AUDUSD=X": "audusd",
    "USDCAD=X": "usdcad",
    "NZDUSD=X": "nzdusd",
    "USDCHF=X": "usdchf",
    "EURGBP=X": "eurgbp",
    "GBPJPY=X": "gbpjpy",
    "EURJPY=X": "eurjpy",
}


def _yf_ticker_to_stooq(ticker: str) -> Optional[str]:
    """Převede Yahoo ticker na Stooq format."""
    if ticker in STOOQ_TICKER_MAP:
        return STOOQ_TICKER_MAP[ticker]
    # Fallback: BTC-USD -> btcusd, EURUSD=X -> eurusd
    clean = ticker.replace("-", "").replace("=X", "").lower()
    if clean:
        return clean
    return None


def fetch_yfinance(ticker: str, period: str = "60d", interval: str = "15m") -> pd.DataFrame:
    """Stáhne data z yfinance."""
    try:
        import yfinance as yf
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
        if df.empty or len(df) < 50:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        for c in list(df.columns):
            if "adj" in str(c).lower():
                df = df.drop(columns=[c], errors="ignore")
        if "Volume" not in df.columns:
            df["Volume"] = (df["High"] - df["Low"]) * 100_000
        df.dropna(inplace=True)
        return df
    except Exception:
        return pd.DataFrame()


def fetch_stooq(ticker: str, period: str = "60d", interval: str = "15m") -> pd.DataFrame:
    """
    Stáhne data ze Stooq (fallback).
    Stooq má hlavně denní data (i=d). Intraday (5m, 60m) často vrací "No data".
    Pro backtest použijeme denní data a upscaleme na 15m (24 barů/den) pro kompatibilitu.
    """
    stooq_ticker = _yf_ticker_to_stooq(ticker)
    if not stooq_ticker:
        return pd.DataFrame()

    try:
        # Parse period - Stooq potřebuje min. 300+ dní pro warmup
        days = 400
        if "d" in period:
            days = max(400, int(period.replace("d", "")))
        elif "mo" in period or "month" in period.lower():
            days = max(400, int(period.replace("mo", "").replace("month", "").strip() or "1") * 30)
        elif "y" in period:
            days = max(400, int(period.replace("y", "").strip() or "1") * 365)

        end = datetime.now()
        start = end - timedelta(days=days)
        d1 = start.strftime("%Y%m%d")
        d2 = end.strftime("%Y%m%d")

        url = f"https://stooq.com/q/d/l/?s={stooq_ticker}&d1={d1}&d2={d2}&i=d"
        df = pd.read_csv(url)
        if df.empty or len(df) < 50:
            return pd.DataFrame()

        # Stooq CSV: Date, Open, High, Low, Close (bez Volume)
        df.columns = [c.strip() for c in df.columns]
        required = ["Date", "Open", "High", "Low", "Close"]
        if not all(c in df.columns for c in required):
            return pd.DataFrame()

        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        df["Volume"] = (df["High"] - df["Low"]) * 100_000  # proxy
        df.dropna(inplace=True)

        # Upscale denní -> intraday pro kompatibilitu
        if interval in ("15m", "5m"):
            bars_per_day = 24 if interval == "15m" else 48  # 24x15m nebo 48x5m
            mins = 15 if interval == "15m" else 5
            rows, dates = [], []
            for dt, r in df.iterrows():
                base = pd.Timestamp(dt).replace(hour=0, minute=0, second=0)
                for j in range(bars_per_day):
                    dates.append(base + timedelta(minutes=mins * j))
                    rows.append({"Open": r["Open"], "High": r["High"], "Low": r["Low"], "Close": r["Close"], "Volume": r["Volume"] / bars_per_day})
            df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates))
        elif interval == "4h":
            bars_per_day = 6  # 6 x 4h = 24h
            rows, dates = [], []
            for dt, r in df.iterrows():
                base = pd.Timestamp(dt).replace(hour=0, minute=0, second=0)
                for j in range(bars_per_day):
                    dates.append(base + timedelta(hours=4 * j))
                    rows.append({"Open": r["Open"], "High": r["High"], "Low": r["Low"], "Close": r["Close"], "Volume": r["Volume"] / bars_per_day})
            df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates))

        return df
    except Exception:
        return pd.DataFrame()


def fetch_data(ticker: str, period: str = "60d", interval: str = "15m", use_stooq_fallback: bool = True) -> pd.DataFrame:
    """
    Stáhne OHLCV data. Nejprve yfinance, při selhání Stooq.
    """
    df = fetch_yfinance(ticker, period=period, interval=interval)
    if df.empty or len(df) < 50:
        if use_stooq_fallback:
            df = fetch_stooq(ticker, period=period, interval=interval)
            if not df.empty:
                pass  # Stooq fallback OK
    return df if not df.empty else pd.DataFrame()
