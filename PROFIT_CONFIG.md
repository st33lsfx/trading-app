# 🎯 PROFIT READY – Konfigurace pro reálný zisk (v6.3)

## Co je PROFIT MODE?

- **Whitelist only** – 19 ziskových tickerů (backtest 100% profitable)
- **Confidence 72%+** – jen A+ setupy
- **Min R:R 1.3** – kvalitní risk:reward
- **Blacklist** – 18 ztrátových tickerů vyloučeno
- **Malý účet** – 50–150 Kč/trade, max 3 pozice
- **Daily limits** – target 500 Kč, max loss 200 Kč
- **Slippage max 0.25%** – nekupuj do ztráty
- **Spread max 1.2%** – crypto CFDs

## Backtest výsledky (30d, 15m)

| Metrika | Před | Po |
|---------|------|-----|
| Průměr Return | 2.67% | **14.76%** |
| Ziskových tickerů | 23/45 (51%) | **19/19 (100%)** |
| Průměr WR | 38% | **49%** |
| Průměr PF | 1.2 | **1.8** |

## Realistické cíle (2000 Kč účet)

| Metrika | Cíl | Realisticky |
|---------|-----|-------------|
| Měsíční return | 5–10% | 2–5% (40–100 Kč) |
| Win rate | 55%+ | 50–55% |
| Profit factor | 1.2+ | 1.1–1.3 |
| Max drawdown | < 10% | < 15% |

## Klíčové principy

1. **Kvalita nad kvantitou** – méně obchodů, vyšší confidence
2. **Ochrana kapitálu** – striktní daily limits
3. **Fees** – na 2k budget jsou významné (2–5 Kč/obchod)
4. **Trpělivost** – čekat na A+ setupy

## Nastavení (bot.py)

```python
PROFIT_MODE = True           # Stricter filters
INITIAL_CAPITAL_CZK = 2000   # Tvůj budget
USD_TO_CZK_RATE = 23.0       # Kurz pro Capital.com
```
