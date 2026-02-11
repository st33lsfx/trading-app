# 🎯 PROFIT READY – Konfigurace pro reálný zisk (v6.0)

## Co je PROFIT MODE?

- **Stricter filters** – jen high-confidence setupy (65%+)
- **Malý účet** – 50–150 Kč/trade, max 3 pozice
- **Daily limits** – target 80 Kč (4%), max loss 60 Kč (3%)
- **Confidence boost** – Trend Breakout +12%, Mean Reversion +10%

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
