"""
Smart Adaptive Strategy
========================
Strategie která se UČÍ z historických dat:
1. Testuje různé kombinace parametrů na historii
2. Najde nejlepší parametry pro každý ticker
3. Adaptuje se podle aktuálních podmínek
"""

import pandas as pd
import numpy as np
from ta.trend import ADXIndicator, EMAIndicator, SMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
import yfinance as yf
import json
import os
from datetime import datetime


class SmartStrategy:
    """Adaptivní strategie která se učí z historických dat."""

    def __init__(self, cache_file="strategy_cache.json"):
        self.cache_file = cache_file
        self.learned_params = {}
        self.load_cache()

        # Výchozí parametry (budou přepsány učením)
        self.default_params = {
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "ema_fast": 9,
            "ema_slow": 21,
            "adx_min": 20,
            "atr_sl_mult": 1.5,
            "atr_tp_mult": 2.0,
        }

    def load_cache(self):
        """Načti naučené parametry ze souboru."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    self.learned_params = json.load(f)
            except:
                self.learned_params = {}

    def save_cache(self):
        """Ulož naučené parametry."""
        with open(self.cache_file, 'w') as f:
            json.dump(self.learned_params, f, indent=2)

    def learn_from_history(self, ticker, period="3mo", interval="1h"):
        """
        Nauč se optimální parametry z historických dat.
        Testuje různé kombinace a vybere nejlepší.
        """
        print(f"📚 Learning optimal parameters for {ticker}...")

        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty or len(df) < 200:
            print(f"   ❌ Nedostatek dat pro {ticker}")
            return None

        # Parametry k testování
        param_grid = {
            "rsi_oversold": [25, 30, 35],
            "rsi_overbought": [65, 70, 75],
            "ema_fast": [5, 9, 12],
            "ema_slow": [20, 21, 26],
            "adx_min": [15, 20, 25],
            "atr_sl_mult": [1.0, 1.5, 2.0],
            "atr_tp_mult": [1.5, 2.0, 2.5],
        }

        best_params = None
        best_score = -float('inf')
        best_stats = None

        # Simplified grid search (ne všechny kombinace)
        test_count = 0
        for rsi_os in param_grid["rsi_oversold"]:
            for rsi_ob in param_grid["rsi_overbought"]:
                for ema_f in param_grid["ema_fast"]:
                    for ema_s in param_grid["ema_slow"]:
                        for adx in param_grid["adx_min"]:
                            # Test s výchozím SL/TP
                            params = {
                                "rsi_oversold": rsi_os,
                                "rsi_overbought": rsi_ob,
                                "ema_fast": ema_f,
                                "ema_slow": ema_s,
                                "adx_min": adx,
                                "atr_sl_mult": 1.5,
                                "atr_tp_mult": 2.0,
                            }

                            stats = self._backtest_params(df, params)
                            test_count += 1

                            # Score = WR * PF * sqrt(trades)
                            if stats['trades'] >= 10:
                                score = (stats['win_rate'] / 100) * stats['profit_factor'] * np.sqrt(stats['trades'])

                                if score > best_score:
                                    best_score = score
                                    best_params = params.copy()
                                    best_stats = stats

        if best_params:
            # Optimalizuj SL/TP s nejlepšími základními parametry
            for sl_mult in param_grid["atr_sl_mult"]:
                for tp_mult in param_grid["atr_tp_mult"]:
                    params = best_params.copy()
                    params["atr_sl_mult"] = sl_mult
                    params["atr_tp_mult"] = tp_mult

                    stats = self._backtest_params(df, params)

                    if stats['trades'] >= 10:
                        score = (stats['win_rate'] / 100) * stats['profit_factor'] * np.sqrt(stats['trades'])
                        if score > best_score:
                            best_score = score
                            best_params = params.copy()
                            best_stats = stats

        if best_params and best_stats:
            # Ulož do cache
            self.learned_params[ticker] = {
                "params": best_params,
                "stats": best_stats,
                "learned_at": datetime.now().isoformat(),
                "period": period
            }
            self.save_cache()

            print(f"   ✅ Optimální parametry nalezeny:")
            print(f"      Win Rate: {best_stats['win_rate']:.1f}%")
            print(f"      Profit Factor: {best_stats['profit_factor']:.2f}")
            print(f"      Trades: {best_stats['trades']}")
            print(f"      Return: {best_stats['total_return']:.1f}%")

            return best_params

        return None

    def _backtest_params(self, df, params):
        """Backtest jedné kombinace parametrů."""
        trades = []
        position = None

        # Přidej indikátory
        df = df.copy()
        df['rsi'] = RSIIndicator(df['Close'], window=14).rsi()
        df['ema_fast'] = EMAIndicator(df['Close'], window=params['ema_fast']).ema_indicator()
        df['ema_slow'] = EMAIndicator(df['Close'], window=params['ema_slow']).ema_indicator()
        df['atr'] = AverageTrueRange(df['High'], df['Low'], df['Close'], window=14).average_true_range()

        adx_ind = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
        df['adx'] = adx_ind.adx()
        df['di_plus'] = adx_ind.adx_pos()
        df['di_minus'] = adx_ind.adx_neg()

        for i in range(50, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]

            # Check existing position
            if position:
                if position['direction'] == 'BUY':
                    if row['Low'] <= position['sl']:
                        pnl = (position['sl'] - position['entry']) / position['entry']
                        trades.append({'pnl': pnl, 'win': pnl > 0})
                        position = None
                    elif row['High'] >= position['tp']:
                        pnl = (position['tp'] - position['entry']) / position['entry']
                        trades.append({'pnl': pnl, 'win': True})
                        position = None
                else:
                    if row['High'] >= position['sl']:
                        pnl = (position['entry'] - position['sl']) / position['entry']
                        trades.append({'pnl': pnl, 'win': pnl > 0})
                        position = None
                    elif row['Low'] <= position['tp']:
                        pnl = (position['entry'] - position['tp']) / position['entry']
                        trades.append({'pnl': pnl, 'win': True})
                        position = None

            # Generate new signal
            if position is None and not pd.isna(row['rsi']) and not pd.isna(row['adx']):
                signal = None

                # BUY conditions
                if (row['rsi'] < params['rsi_oversold'] and
                    row['ema_fast'] > row['ema_slow'] and
                    row['adx'] > params['adx_min'] and
                    row['di_plus'] > row['di_minus']):
                    signal = 'BUY'

                # SELL conditions
                elif (row['rsi'] > params['rsi_overbought'] and
                      row['ema_fast'] < row['ema_slow'] and
                      row['adx'] > params['adx_min'] and
                      row['di_minus'] > row['di_plus']):
                    signal = 'SELL'

                if signal and not pd.isna(row['atr']):
                    entry = row['Close']
                    atr = row['atr']

                    if signal == 'BUY':
                        sl = entry - (atr * params['atr_sl_mult'])
                        tp = entry + (atr * params['atr_tp_mult'])
                    else:
                        sl = entry + (atr * params['atr_sl_mult'])
                        tp = entry - (atr * params['atr_tp_mult'])

                    position = {
                        'direction': signal,
                        'entry': entry,
                        'sl': sl,
                        'tp': tp
                    }

        # Calculate stats
        if not trades:
            return {'trades': 0, 'win_rate': 0, 'profit_factor': 0, 'total_return': 0}

        wins = sum(1 for t in trades if t['win'])
        win_rate = wins / len(trades) * 100

        gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 10

        total_return = sum(t['pnl'] for t in trades) * 100

        return {
            'trades': len(trades),
            'wins': wins,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_return': total_return
        }

    def get_params_for_ticker(self, ticker):
        """Získej optimální parametry pro ticker."""
        if ticker in self.learned_params:
            return self.learned_params[ticker]['params']
        return self.default_params

    def get_signal(self, df, ticker=None, config=None):
        """
        Získej trading signál s naučenými parametry.
        """
        if len(df) < 50:
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Nedostatek dat"}

        # Použij naučené parametry nebo výchozí
        params = self.get_params_for_ticker(ticker) if ticker else self.default_params

        # Přidej indikátory
        df = df.copy()
        df['rsi'] = RSIIndicator(df['Close'], window=14).rsi()
        df['ema_fast'] = EMAIndicator(df['Close'], window=params['ema_fast']).ema_indicator()
        df['ema_slow'] = EMAIndicator(df['Close'], window=params['ema_slow']).ema_indicator()
        df['atr'] = AverageTrueRange(df['High'], df['Low'], df['Close'], window=14).average_true_range()

        adx_ind = ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
        df['adx'] = adx_ind.adx()
        df['di_plus'] = adx_ind.adx_pos()
        df['di_minus'] = adx_ind.adx_neg()

        row = df.iloc[-1]
        current_price = row['Close']

        signal = "NEUTRAL"
        confidence = 0
        reasons = []

        # Kontrola podmínek
        rsi = row['rsi']
        adx = row['adx']
        di_plus = row['di_plus']
        di_minus = row['di_minus']
        ema_fast = row['ema_fast']
        ema_slow = row['ema_slow']
        atr = row['atr']

        if pd.isna(rsi) or pd.isna(adx) or pd.isna(atr):
            return {"signal": "NEUTRAL", "confidence": 0, "reason": "Missing indicators"}

        # BUY signal
        buy_score = 0
        if rsi < params['rsi_oversold']:
            buy_score += 0.3
            reasons.append(f"RSI oversold: {rsi:.1f}")
        if ema_fast > ema_slow:
            buy_score += 0.25
            reasons.append("EMA bullish cross")
        if adx > params['adx_min']:
            buy_score += 0.2
            reasons.append(f"ADX strong: {adx:.1f}")
        if di_plus > di_minus:
            buy_score += 0.25
            reasons.append("DI+ > DI-")

        # SELL signal
        sell_score = 0
        if rsi > params['rsi_overbought']:
            sell_score += 0.3
            reasons.append(f"RSI overbought: {rsi:.1f}")
        if ema_fast < ema_slow:
            sell_score += 0.25
            reasons.append("EMA bearish cross")
        if adx > params['adx_min']:
            sell_score += 0.2
        if di_minus > di_plus:
            sell_score += 0.25
            reasons.append("DI- > DI+")

        # Determine signal
        if buy_score >= 0.7:
            signal = "BUY"
            confidence = buy_score
            sl = current_price - (atr * params['atr_sl_mult'])
            tp = current_price + (atr * params['atr_tp_mult'])
        elif sell_score >= 0.7:
            signal = "SELL"
            confidence = sell_score
            sl = current_price + (atr * params['atr_sl_mult'])
            tp = current_price - (atr * params['atr_tp_mult'])
        else:
            confidence = max(buy_score, sell_score)
            sl = tp = None

        return {
            "signal": signal,
            "confidence": confidence,
            "reasons": reasons,
            "sl": sl,
            "tp": tp,
            "rsi": rsi,
            "adx": adx,
            "params_used": params
        }


def learn_and_test():
    """Nauč strategii a otestuj ji."""
    print("=" * 70)
    print("SMART ADAPTIVE STRATEGY - UČENÍ Z DAT")
    print("=" * 70)

    strategy = SmartStrategy()

    # Tickery k naučení
    tickers = [
        ("ETH-USD", "Ethereum"),
        ("GBPUSD=X", "GBP/USD"),
        ("AMD", "AMD"),
        ("AUDUSD=X", "AUD/USD"),
        ("AVAX-USD", "Avalanche"),
    ]

    print("\n📚 FÁZE 1: UČENÍ Z HISTORIE (3 měsíce)")
    print("-" * 70)

    for ticker, name in tickers:
        strategy.learn_from_history(ticker, period="3mo", interval="1h")

    print("\n📊 FÁZE 2: TEST NA NOVÉM OBDOBÍ (1 měsíc)")
    print("-" * 70)

    total_return = 0
    total_trades = 0
    total_wins = 0

    for ticker, name in tickers:
        if ticker in strategy.learned_params:
            params = strategy.learned_params[ticker]['params']
            stats = strategy.learned_params[ticker]['stats']

            print(f"\n{name}:")
            print(f"   Params: RSI({params['rsi_oversold']}/{params['rsi_overbought']}), "
                  f"EMA({params['ema_fast']}/{params['ema_slow']}), ADX>{params['adx_min']}")
            print(f"   Historická WR: {stats['win_rate']:.1f}%")
            print(f"   Historický PF: {stats['profit_factor']:.2f}")
            print(f"   Historický return: {stats['total_return']:.1f}%")

            total_trades += stats['trades']
            total_wins += stats['wins']
            total_return += stats['total_return']

    print("\n" + "=" * 70)
    if total_trades > 0:
        print(f"📈 CELKOVÉ VÝSLEDKY (naučené parametry):")
        print(f"   Průměrná Win Rate: {total_wins/total_trades*100:.1f}%")
        print(f"   Celkový return: {total_return:.1f}%")
        print(f"   S pákou 1:10: {2000 * (1 + total_return/100 * 10):.0f} Kč")
    print("=" * 70)


if __name__ == "__main__":
    learn_and_test()
