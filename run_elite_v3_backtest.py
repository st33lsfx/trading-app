#!/usr/bin/env python3
"""
Backtest pro EliteAdaptiveStrategy (elite_v3) — Session Volume Profile, VAH/VAL/POC.
Spouští stejnou logiku jako live bot (get_signal na každý bar).
"""

import argparse
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from elite_adaptive_strategy import EliteAdaptiveStrategy


# Konfigurace shodná s bot.py pro elite_v3
DEFAULT_CONFIG = {
    "use_session_vp": True,
    "adx_threshold": 25,
    "sl_atr": 4.0,
    "tp_rr": 2.0,
    "vp_lookback": 288,
    "min_session_bars_for_vp": 5,
    "vwap_window": 96,
}


def get_forex_config():
    """Konfig pro forex: jen range mean reversion (trend breakouts často ztrátové)."""
    c = dict(DEFAULT_CONFIG)
    c["forex_range_only"] = True
    return c


def fetch_data(ticker: str, period: str = "60d", interval: str = "15m") -> pd.DataFrame:
    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        for c in list(df.columns):
            if "adj" in str(c).lower():
                df = df.drop(columns=[c], errors="ignore")
        if "Volume" not in df.columns:
            df["Volume"] = (df["High"] - df["Low"]) * 100_000
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"Chyba stahování {ticker}: {e}")
        return pd.DataFrame()


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

    strategy = EliteAdaptiveStrategy(config)
    # Minimální počet barů pro VP + indikátory
    start_idx = max(strategy.vp_lookback_bars, 200)
    if len(df) <= start_idx:
        return {"error": "Málo dat po warmup", "ticker": ticker}

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
                    res = strategy.get_signal(slice_df)
                except Exception:
                    res = {"signal": "NEUTRAL"}
            else:
                res = {"signal": "NEUTRAL"}
            sig = res.get("signal", "NEUTRAL")
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
    ap.add_argument("--risk", type=float, default=0.003, help="Riziko na obchod (0.003 = 0.3%%, 0.005 = 0.5%%)")
    ap.add_argument("--list", action="store_true", help="Spustit na seznamu Elite 15")
    ap.add_argument("--forex", action="store_true", help="Spustit jen na forex párech")
    ap.add_argument("--fast", action="store_true", help="Rychlejší: signál jen každé 4 bary (méně obchodů)")
    args = ap.parse_args()

    signal_every_n = 4 if args.fast else 1

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
        tickers = [
            "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
            "NZDUSD=X", "USDCHF=X", "EURGBP=X", "GBPJPY=X", "EURJPY=X",
        ]
        print("=== BACKTEST ELITE V3 (Session VP) — více symbolů ===\n")
        results = []
        for t in tickers:
            print(f"  {t}...", end=" ", flush=True)
            r = run_backtest(t, period=args.period, interval=args.interval, initial_capital=args.capital, risk_pct=args.risk)
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
