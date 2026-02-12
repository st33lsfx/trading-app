# 📊 Data Sources & Pro Trading Inspiration (v6.3)

## Co už máme

| Zdroj | Data | Použití |
|-------|------|---------|
| **Yahoo Finance** | OHLCV, Volume, Analyst Ratings, News | Strategie, indikátory, sentiment |
| **Stooq** | OHLCV (fallback) | Když Yahoo selže |
| **ForexFactory** | Economic Calendar | News filter (30 min před High Impact) |
| **exchangerate-api.com** | USD/CZK | Sizing |
| **Capital.com API** | Live bid/offer, pozice, ordery | Exekuce |

### Indikátory (z OHLCV)

- **VWAP** + bands (volume-weighted)
- **Volume Profile** (POC, VAH, VAL)
- ADX, EMA, RSI, OBV, ADL
- ATR, Bollinger Bands

---

## Odkud berou inspiraci profesionální traderi

### 1. **Order Flow / Delta** (institucionální)
- CVD (Cumulative Volume Delta) – buy vs sell tlak
- Vyžaduje: tick data nebo Level 2
- **Pro CFD:** Capital.com nemá order flow API – použít proxy (OBV, ADL)

### 2. **Funding Rate** (krypto)
- Binance, Bybit – sentiment long/short
- Vysoké funding = dlouhé přetížené → reverzní signál
- **Free API:** `https://fapi.binance.com/fapi/v1/fundingRate`

### 3. **Crypto Fear & Greed Index**
- Alternative.me – denní sentiment 0–100
- **Free API:** `https://api.alternative.me/fng/`

### 4. **BTC Dominance**
- Podíl BTC z celkové crypto kapitalizace
- Altseason když dominance klesá
- Yahoo: `BTC-USD`, `^TOTAL2` (CoinMarketCap)

### 5. **Open Interest** (futures)
- CryptoQuant, Binance – pozice institucí
- Růst OI + růst ceny = silný trend

### 6. **Lepší volume**
- Yahoo volume u crypto je často syntetický
- CoinGecko / Binance – reálnější volume

### 7. **Multi-timeframe**
- Vyšší TF (4h, 1D) pro trend
- Už máme: `fetch_trend_data()` 4h

### 8. **Correlation**
- BTC vs altcoiny – když BTC padá, většina altů taky
- Už máme: `check_correlation()`

---

## Doporučení pro profi bota (priorita)

### 🟢 Implementováno (v6.3)

| # | Zlepšení | Zdroj | Status |
|---|----------|-------|--------|
| 1 | **Crypto Fear & Greed** | alternative.me | ✅ Skip při Extreme Fear (<20) nebo Greed (>80) |
| 2 | **Economic calendar** | ForexFactory | ✅ NFP, FOMC, CPI = 60 min window; crypto vždy USD |
| 3 | **Funding rate filter** | Binance API | ✅ Skip při funding > 0.05% (overcrowded) |

(viz `crypto_sentiment.py`)

### 🟡 Střední (půl dne)

| # | Zlepšení | Zdroj | Dopad |
|---|----------|-------|-------|
| 4 | **BTC dominance** | Yahoo ^TOTAL2 | Altseason mode – větší pozice v altech |
| 5 | **CoinGecko fallback** | coingecko.com | Lepší OHLCV když Yahoo selže |
| 6 | **Vylepšit news filter** | Přidat key slova (FOMC, NFP, CPI) | Blokovat 60 min místo 30 |

### 🔴 Delší (1+ den)

| # | Zlepšení | Zdroj | Dopad |
|---|----------|-------|-------|
| 7 | **WebSocket live data** | Capital.com streaming | Rychlejší reakce na cenu |
| 8 | **On-chain (whale alerts)** | Glassnode (placené) | Volitelné pro pokročilé |

---

## Přehled volných API

| API | Endpoint | Limit | Data |
|-----|----------|-------|------|
| Alternative.me | /fng/ | Volné | Fear & Greed |
| Binance | /fapi/v1/fundingRate | Volné | Funding rate |
| Binance | /api/v3/klines | Volné | OHLCV (lepší než Yahoo pro crypto) |
| CoinGecko | /coins/{id}/ohlc | ~10–30/min | OHLC |
| ForexFactory | faireconomy.media | Volné | Economic calendar |

---

## Shrnutí

**Aktuální stav:** Solidní základ (VP, VWAP, VIX, economic calendar).

**Nejvyšší priorita pro „profi“ feel:**
1. Crypto Fear & Greed filter
2. Funding rate filter
3. Lepší blokování během high-impact news (NFP, FOMC)

Tyto 3 změny přidají datové zdroje, které používají profesionální krypto traderi, bez placených API.
