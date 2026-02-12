# Entry Quality Check - Co sledovat po otevření pozice

## ✅ Normální (OK)

**Okamžitá ztráta 0.05-0.3%:**

- Spread (bid/ask): 0.05-0.15%
- Trading fees: ~0.05-0.1%
- **Celkem:** ~0.1-0.3% = NORMÁLNÍ

**Příklad:**

```
Entry BTC @ $100,000
Po 1 sekundě: -$150 (-0.15%)
→ OK! To je jen spread
```

---

## ❌ Problém (ŠPATNĚ)

**Okamžitá ztráta 1-5%+:**

- ⚠️ Špatný entry timing (vstup na top/bottom)
- ⚠️ Velký slippage (low liquidity)
- ⚠️ SL příliš blízko entry

**Příklad:**

```
Entry BTC @ $100,000
Po 1 sekundě: -$2,000 (-2%)
→ PROBLÉM! Entry na špatnou cenu nebo SL trigger risk
```

---

## 🎯 Jak bot vstupuje (Capital.com)

1. **Signal generován** na close ceně
2. **Market order** placován (okamžitý vstup)
3. **Entry price** = **offer** (BUY) nebo **bid** (SELL)
4. **Spread loss** = rozdíl mezi bid/offer (~0.05-0.15%)

### Stop Loss nastavení:

| Asset                 | Min SL Distance | ATR Multiplier | Typical SL % |
| --------------------- | --------------- | -------------- | ------------ |
| **Crypto** (BTC, ETH) | 2.5%            | 8.0x           | **4-8%**     |
| **Crypto** (altcoiny) | 2.5%            | 4.0x           | **3-6%**     |

**Poznámka:** SL je daleko = méně false breakouts, ale vyšší risk na trade.

---

## 💡 Scale-Out výhoda

**Bez scale-out:**

```
Entry: $100,000
SL: $96,000 (-4%)
TP: $108,000 (+8%)
→ Musíš čekat na plný TP (+8%)
```

**Se scale-out (balanced):**

```
Entry: $100,000
SL: $96,000 (-4%)

TP1 @ $101,200 (+1.2%): Close 30% → Lock $360
TP2 @ $102,000 (+2.0%): Close 35% → Lock $700

→ Locks $1,060 profit BEFORE full TP
→ Snižuje risk reversal
```

---

## 🔍 Jak kontrolovat kvalitu entry

**Po otevření pozice zkontroluj:**

1. **P&L po 5-10 sekundách:**
   - ✅ -0.1% až -0.3% = OK (spread)
   - ⚠️ -0.5% až -1% = velký spread
   - ❌ -1%+ = špatný entry!

2. **SL vzdálenost:**
   - ✅ 3-8% na crypto = OK
   - ⚠️ 10%+ = příliš široký
   - ❌ <2% = příliš úzký

---

## 🚀 Závěr

✅ **0.1-0.3% ztráta hned po vstupu = NORMÁLNÍ** (spread + fees)  
❌ **1%+ ztráta hned po vstupu = PROBLÉM** (špatný timing)  
🎯 **Scale-out pomůže** lock profit rychleji!
