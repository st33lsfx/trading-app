#!/usr/bin/env python3
"""
Backtest pro EliteAdaptiveStrategy (elite_v3) — Session Volume Profile, VAH/VAL/POC.
Spouští stejnou logiku jako live bot (get_signal na každý bar).
"""

import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from elite_adaptive_strategy import EliteAdaptiveStrategy
from data_fetcher import fetch_data as fetch_market_data


# Konfigurace v4.0 CRYPTO PERFECT
DEFAULT_CONFIG = {
    "use_session_vp": True,
    "adx_threshold": 28,
    "sl_atr": 4.0,
    "tp_rr": 2.0,
    "vp_lookback": 96,   # 1 den (rychlejší, crypto-friendly)
    "min_session_bars_for_vp": 5,
    "vwap_window": 96,
}


def get_forex_config():
    """Konfig pro forex: VWAP mode (no VP), wider SL, simple mean reversion."""
    c = dict(DEFAULT_CONFIG)
    c["forex_mode"] = True  # Skip VP, use VWAP + EMA + RSI only
    c["sl_atr"] = 5.0  # wider SL pro forex volatilitu + spread
    c["tp_rr"] = 2.0  # standard R:R
    c["adx_threshold"] = 25
    return c


def fetch_data(ticker: str, period: str = "60d", interval: str = "15m") -> pd.DataFrame:
    """yfinance + Stooq fallback (když yfinance nevrátí data)."""
    df = fetch_market_data(ticker, period=period, interval=interval)
    return df


def run_backtest(
    ticker: str,
    period: str = "60d",
    interval: str = "15m",
    initial_capital: float = 10_000.0,
    risk_pct: float = 0.02,
    config: dict = None,
    fee_pct: float = 0.0006,
    signal_every_n: int = 1,
) -> dict:
    config = config or DEFAULT_CONFIG
    df = fetch_data(ticker, period=period, interval=interval)
    if df.empty or len(df) < 300:
        return {"error": f"Málo dat ({len(df)} barů)", "ticker": ticker}

    # Detect asset class for strategy mode
    asset_class = "forex" if config.get("forex_mode") else "crypto"

    strategy = EliteAdaptiveStrategy(config)
    # Minimální počet barů pro VP + indikátory
    start_idx = max(strategy.vp_lookback_bars, 200)
    if len(df) <= start_idx:
        return {"error": "Málo dat po warmup", "ticker": ticker}

    # Pre-calculate indicators once (much faster than per-bar)
    df = strategy.add_indicators(df)

    balance = initial_capital
    position = None
    trades = []
    equity_curve = [balance]
    peak = balance

    for i in range(start_idx, len(df)):
        slice_df = df.iloc[: i + 1].copy()
        row = df.iloc[i]
        ts = df.index[i]

        # ——— Řízení otevřené pozice ———
        if position:
            high, low, close = row["High"], row["Low"], row["Close"]
            pnl = None
            exit_reason = None
            exit_price = close

            if position["type"] == "BUY":
                if low <= position["sl"]:
                    exit_price = position["sl"]
                    exit_reason = "SL"
                elif high >= position["tp"]:
                    exit_price = position["tp"]
                    exit_reason = "TP"
            else:
                if high >= position["sl"]:
                    exit_price = position["sl"]
                    exit_reason = "SL"
                elif low <= position["tp"]:
                    exit_price = position["tp"]
                    exit_reason = "TP"

            if exit_reason:
                if position["type"] == "BUY":
                    pnl = (exit_price - position["entry"]) * position["size"]
                else:
                    pnl = (position["entry"] - exit_price) * position["size"]
                cost = position["entry"] * position["size"] * fee_pct * 2
                pnl -= cost
                balance += pnl
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": ts,
                    "type": position["type"],
                    "entry": position["entry"],
                    "exit": exit_price,
                    "pnl": pnl,
                    "reason": exit_reason,
                })
                position = None
                peak = max(peak, balance)

        # ——— Nový vstup (jen když nemáme pozici) ———
        if position is None:
            if signal_every_n <= 1 or (i - start_idx) % signal_every_n == 0:
                try:
                    res = strategy.get_signal(slice_df, asset_class=asset_class)
                except Exception:
                    res = {"signal": "NEUTRAL"}
            else:
                res = {"signal": "NEUTRAL"}
            sig = res.get("signal", "NEUTRAL")
            conf = res.get("confidence", 0)
            # v4.0 CRYPTO PERFECT: min confidence 0.68
            if sig in ("BUY", "SELL") and conf < 0.68:
                sig = "NEUTRAL"
            if sig in ("BUY", "SELL") and res.get("sl") is not None and res.get("tp") is not None:
                close_px = row["Close"]
                sl = float(res["sl"])
                tp = float(res["tp"])
                risk_amt = balance * risk_pct
                if sig == "BUY":
                    dist = close_px - sl
                else:
                    dist = sl - close_px
                if dist > 0:
                    size = risk_amt / dist
                    position = {
                        "type": sig,
                        "entry": close_px,
                        "sl": sl,
                        "tp": tp,
                        "size": size,
                        "entry_time": ts,
                    }
        equity_curve.append(balance)

    # Zavření pozice na konci dat
    if position:
        close_px = df.iloc[-1]["Close"]
        if position["type"] == "BUY":
            pnl = (close_px - position["entry"]) * position["size"]
        else:
            pnl = (position["entry"] - close_px) * position["size"]
        balance += pnl
        trades.append({
            "entry_time": position["entry_time"],
            "exit_time": df.index[-1],
            "type": position["type"],
            "entry": position["entry"],
            "exit": close_px,
            "pnl": pnl,
            "reason": "End",
        })

    # Metriky
    eq = np.array(equity_curve)
    peak_curve = np.maximum.accumulate(eq)
    dd = (peak_curve - eq) / np.where(peak_curve > 0, peak_curve, 1)
    max_dd_pct = float(np.nanmax(dd) * 100) if len(dd) else 0
    total_return_pct = (balance - initial_capital) / initial_capital * 100
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / n * 100 if n else 0
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0)

    return {
        "ticker": ticker,
        "period": period,
        "interval": interval,
        "total_trades": n,
        "win_rate": win_rate,
        "profit_factor": round(profit_factor, 2),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "final_balance": round(balance, 2),
        "trades": trades,
    }


def main():
    ap = argparse.ArgumentParser(description="Backtest Elite v3 (Session VP, VAH/VAL/POC)")
    ap.add_argument("--ticker", default="BTC-USD", help="Symbol (Yahoo)")
    ap.add_argument("--period", default="60d", help="Období (60d, 1y)")
    ap.add_argument("--interval", default="15m", help="Timeframe (15m, 1h)")
    ap.add_argument("--capital", type=float, default=10_000, help="Počáteční kapitál")
    ap.add_argument("--risk", type=float, default=0.02, help="Riziko na obchod (0.02 = 2%%, standard pro malý účet)")
    ap.add_argument("--list", action="store_true", help="Spustit na seznamu Elite 15")
    ap.add_argument("--forex", action="store_true", help="Spustit jen na forex párech")
    ap.add_argument("--all", action="store_true", help="Spustit CRYPTO + FOREX (kombinovaný backtest)")
    ap.add_argument("--fast", action="store_true", help="Rychlejší: signál jen každé 4 bary (méně obchodů)")
    args = ap.parse_args()

    signal_every_n = 4 if args.fast else 1

    # === CRYPTO + FOREX kombinovaný backtest ===
    if args.all:
        # v7.0: 50 CRYPTO (forex vypnutý — ztratový)
        crypto_tickers = [
            "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "DOGE-USD", "ADA-USD",
            "AVAX-USD", "DOT-USD", "LINK-USD", "NEAR-USD", "ATOM-USD", "XLM-USD", "LTC-USD",
            "TRX-USD", "ICP-USD", "ALGO-USD", "SUI-USD", "INJ-USD", "HBAR-USD",
            "SAND-USD", "SHIB-USD", "PEPE-USD", "ARB-USD", "OP-USD",
            "FIL-USD", "VET-USD", "RUNE-USD", "SEI-USD", "WLD-USD",
            "AAVE-USD", "MANA-USD", "GALA-USD", "AXS-USD", "EOS-USD",
            "MKR-USD", "APE-USD", "CRV-USD", "LDO-USD", "ENS-USD",
            "IMX-USD", "FLOKI-USD", "FET-USD", "RNDR-USD", "STX-USD",
            "EGLD-USD", "FLOW-USD", "CHZ-USD", "ZIL-USD", "KAS-USD",
        ]
        period = args.period if args.period != "60d" else "30d"
        print(f"=== BACKTEST ELITE V3 — 50 CRYPTO (2% risk) ===\n")
        results = []
        
        for t in crypto_tickers:
            print(f"  {t}...", end=" ", flush=True)
            r = run_backtest(t, period=period, interval=args.interval, initial_capital=args.capital, risk_pct=args.risk, signal_every_n=signal_every_n)
            if "error" in r:
                print(r["error"])
            else:
                print(f"Trades: {r['total_trades']} | WR: {r['win_rate']:.0f}% | PF: {r['profit_factor']} | Return: {r['total_return_pct']}%")
                results.append({**r, "asset_class": "Crypto"})
        
        if results:
            # Build summary rows with asset_class
            rows = []
            for r in results:
                row = {k: v for k, v in r.items() if k != "trades"}
                row["asset_class"] = r.get("asset_class", "")
                rows.append(row)
            df = pd.DataFrame(rows)
            print("\n" + "="*60)
            print(f"--- SOUHRN ({len(results)} crypto) ---")
            print(df.to_string(index=False))
            total_trades = sum(r["total_trades"] for r in results)
            avg_return = df["total_return_pct"].mean()
            profitable = len(df[df["total_return_pct"] > 0])
            losing = len(df[df["total_return_pct"] <= 0])
            avg_wr = df["win_rate"].mean()
            avg_pf = df["profit_factor"].mean()
            best = df.loc[df["total_return_pct"].idxmax()]
            worst = df.loc[df["total_return_pct"].idxmin()]
            print(f"\n📊 Celkem obchodů: {total_trades}")
            print(f"📈 Průměr Return: {avg_return:.2f}%")
            print(f"   Ziskových: {profitable}/{len(results)} | Ztrátových: {losing}/{len(results)}")
            print(f"   Průměr WR: {avg_wr:.0f}% | Průměr PF: {avg_pf:.1f}")
            print(f"   Nejlepší: {best['ticker']} +{best['total_return_pct']}%")
            print(f"   Nejhorší: {worst['ticker']} {worst['total_return_pct']}%")
        return

    if args.forex:
        tickers = [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
            "NZDUSD=X", "USDCHF=X", "EURGBP=X", "GBPJPY=X", "EURJPY=X",
        ]
        period = args.period if args.period != "60d" else "30d"
        print("=== BACKTEST ELITE V3 — FOREX (Session VP, range-only) ===\n")
        results = []
        fconfig = get_forex_config()
        for t in tickers:
            print(f"  {t}...", end=" ", flush=True)
            r = run_backtest(t, period=period, interval=args.interval, initial_capital=args.capital, risk_pct=args.risk, signal_every_n=signal_every_n, config=fconfig)
            if "error" in r:
                print(r["error"])
            else:
                print(f"Trades: {r['total_trades']} | WR: {r['win_rate']:.0f}% | PF: {r['profit_factor']} | Return: {r['total_return_pct']}%")
                results.append(r)
        if results:
            df = pd.DataFrame([{k: v for k, v in x.items() if k != "trades"} for x in results])
            print("\n--- Souhrn forex ---")
            print(df.to_string(index=False))
            print(f"\nPrůměr Return: {df['total_return_pct'].mean():.2f}% | Celkem obchodů: {df['total_trades'].sum()}")
        return

    if args.list:
        crypto_tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]
        forex_tickers = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X"]
        tickers = crypto_tickers + forex_tickers
        print("=== BACKTEST ELITE V3 — Crypto (VP) + Forex (VWAP) ===\n")
        results = []
        fconfig = get_forex_config()
        for t in tickers:
            print(f"  {t}...", end=" ", flush=True)
            cfg = fconfig if "=X" in t else None  # Forex používají forex_mode
            r = run_backtest(t, period=args.period, interval=args.interval, initial_capital=args.capital, risk_pct=args.risk, config=cfg, signal_every_n=signal_every_n)
            if "error" in r:
                print(r["error"])
            else:
                print(f"Trades: {r['total_trades']} | WR: {r['win_rate']:.0f}% | PF: {r['profit_factor']} | Return: {r['total_return_pct']}%")
                results.append(r)
        if results:
            df = pd.DataFrame([{k: v for k, v in x.items() if k != "trades"} for x in results])
            print("\n--- Souhrn ---")
            print(df.to_string(index=False))
            print(f"\nPrůměr Return: {df['total_return_pct'].mean():.2f}% | Celkem obchodů: {df['total_trades'].sum()}")
        return

    print(f"=== Backtest Elite v3: {args.ticker} ({args.period}, {args.interval}) ===\n")
    r = run_backtest(
        args.ticker,
        period=args.period,
        interval=args.interval,
        initial_capital=args.capital,
        risk_pct=args.risk,
    )
    if "error" in r:
        print("Chyba:", r["error"])
        return
    print(f"Obchody:    {r['total_trades']}")
    print(f"Win rate:   {r['win_rate']:.2f}%")
    print(f"Profit factor: {r['profit_factor']}")
    print(f"Return:     {r['total_return_pct']}%")
    print(f"Max DD:     {r['max_drawdown_pct']}%")
    print(f"Konec kapitál: {r['final_balance']:.2f}")
    if r["trades"]:
        print("\nPosledních 5 obchodů:")
        for t in r["trades"][-5:]:
            print(f"  {t['type']} @ {t['entry']:.4f} -> {t['reason']} | PnL: {t['pnl']:.2f}")


if __name__ == "__main__":
    main()
