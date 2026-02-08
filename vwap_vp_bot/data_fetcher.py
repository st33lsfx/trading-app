"""
Data Fetcher Module
====================
- Fetches historical OHLCV data from Binance API (for local use)
- Generates realistic synthetic BTC/USDT data for backtesting
  when API is unavailable (uses jump-diffusion + GARCH volatility clustering)
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


def fetch_binance_klines(symbol='BTCUSDT', interval='15m',
                         start_date='2021-01-01', end_date=None,
                         limit_per_request=1000):
    """
    Fetch historical kline data from Binance public API.
    Use this when running locally with network access.

    Returns DataFrame with columns:
    [timestamp, open, high, low, close, volume, close_time,
     quote_volume, trades, taker_buy_base, taker_buy_quote]
    """
    import requests

    base_url = 'https://api.binance.com/api/v3/klines'

    start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
    if end_date:
        end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)
    else:
        end_ts = int(datetime.now().timestamp() * 1000)

    all_data = []
    current_ts = start_ts

    while current_ts < end_ts:
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': current_ts,
            'endTime': end_ts,
            'limit': limit_per_request
        }

        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            break

        all_data.extend(data)
        current_ts = data[-1][0] + 1  # Next ms after last candle

        if len(data) < limit_per_request:
            break

    if not all_data:
        raise ValueError("No data fetched from Binance")

    df = pd.DataFrame(all_data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades',
        'taker_buy_base', 'taker_buy_quote', 'ignore'
    ])

    for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume',
                'taker_buy_base', 'taker_buy_quote']:
        df[col] = df[col].astype(float)

    df['trades'] = df['trades'].astype(int)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df.drop(columns=['ignore'], inplace=True)

    return df


def generate_synthetic_btcusdt(start_date='2021-01-01', end_date='2025-01-01',
                                interval_minutes=15, seed=42):
    """
    Generate realistic synthetic BTC/USDT 15-min OHLCV data using:
    - Geometric Brownian Motion with mean reversion
    - GARCH(1,1)-like volatility clustering
    - Jump diffusion (Merton model) for sudden moves
    - Realistic volume patterns (session-based, spike on moves)
    - Microstructure: proper OHLC from intra-bar simulation

    This produces data with realistic statistical properties:
    fat tails, volatility clustering, volume-price correlation,
    session patterns, trending + ranging regimes.
    """
    np.random.seed(seed)

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    n_bars = int((end - start).total_seconds() / (interval_minutes * 60))

    # --- Parameters calibrated to real BTC/USDT 15-min data ---
    dt = interval_minutes / (365.25 * 24 * 60)  # Fraction of year

    # Base drift (annualized ~40% for BTC bull/bear cycles)
    mu_annual = 0.30
    mu = mu_annual * dt

    # GARCH(1,1) parameters for volatility clustering
    omega = 1e-7       # Long-run variance floor
    alpha = 0.08       # Shock sensitivity
    beta = 0.90        # Persistence
    vol_annual = 0.70  # Annualized base vol ~70%
    var_t = (vol_annual * np.sqrt(dt)) ** 2

    # Jump parameters (Merton)
    jump_intensity = 0.005   # ~0.5% chance of jump per bar
    jump_mean = 0.0          # Mean jump (symmetric)
    jump_std = 0.03          # Jump magnitude std

    # Mean reversion (weak - pulls toward long-term trend)
    mean_rev_speed = 0.0001

    # Regime switching: trending vs ranging
    regime_duration_bars = int(7 * 24 * 4)  # ~1 week per regime avg

    # --- Generate price path ---
    prices = np.zeros(n_bars + 1)
    prices[0] = 29000.0  # Starting price (Jan 2021-ish)

    variances = np.zeros(n_bars + 1)
    variances[0] = var_t

    # Pre-generate randoms
    z_price = np.random.standard_normal(n_bars)
    z_jump_uniform = np.random.uniform(0, 1, n_bars)
    z_jump_size = np.random.standard_normal(n_bars)

    # Regime states
    regimes = np.zeros(n_bars, dtype=int)  # 0=ranging, 1=trend_up, 2=trend_down
    current_regime = 1
    regime_counter = 0

    for i in range(n_bars):
        # Update regime
        regime_counter += 1
        if regime_counter > regime_duration_bars:
            if np.random.random() < 0.03:  # ~3% switch probability after min duration
                current_regime = np.random.choice([0, 1, 2], p=[0.35, 0.40, 0.25])
                regime_counter = 0
        regimes[i] = current_regime

        # Regime-dependent drift
        if current_regime == 0:  # Ranging
            regime_mu = 0.0
        elif current_regime == 1:  # Trend up
            regime_mu = mu * 2.5
        else:  # Trend down
            regime_mu = -mu * 2.0

        # GARCH variance update
        shock = z_price[i] * np.sqrt(variances[i])
        variances[i+1] = omega + alpha * shock**2 + beta * variances[i]
        variances[i+1] = max(variances[i+1], 1e-10)

        # Jump component
        jump = 0.0
        if z_jump_uniform[i] < jump_intensity:
            jump = jump_mean + jump_std * z_jump_size[i]
            # Increase variance after jump
            variances[i+1] *= 1.5

        # Mean reversion toward log-trend
        log_trend = np.log(29000) + mu_annual * (i * dt)
        mean_rev = mean_rev_speed * (log_trend - np.log(max(prices[i], 1)))

        # Price update (geometric)
        log_return = regime_mu + mean_rev + shock + jump
        prices[i+1] = prices[i] * np.exp(log_return)
        prices[i+1] = max(prices[i+1], 100)  # Floor

    close_prices = prices[1:]
    open_prices = prices[:-1]

    # --- Generate realistic OHLC from close-to-close ---
    # Intra-bar high/low using Parkinson estimator relationship
    intra_vol = np.sqrt(variances[1:]) * 1.2  # Intra-bar vol slightly higher

    high_prices = np.maximum(open_prices, close_prices) * (1 + np.abs(np.random.standard_normal(n_bars)) * intra_vol * 0.5)
    low_prices = np.minimum(open_prices, close_prices) * (1 - np.abs(np.random.standard_normal(n_bars)) * intra_vol * 0.5)

    # Ensure OHLC consistency
    high_prices = np.maximum(high_prices, np.maximum(open_prices, close_prices))
    low_prices = np.minimum(low_prices, np.minimum(open_prices, close_prices))
    low_prices = np.maximum(low_prices, 1.0)

    # --- Generate realistic volume ---
    # Base volume with session patterns
    timestamps = pd.date_range(start=start, periods=n_bars, freq=f'{interval_minutes}min')
    hours = timestamps.hour

    # Session volumes (UTC): Asia (0-8), Europe (8-16), US (16-24)
    session_multiplier = np.ones(n_bars)
    for i_bar in range(n_bars):
        h = hours[i_bar]
        if 13 <= h <= 21:    # US session (peak)
            session_multiplier[i_bar] = 1.5
        elif 7 <= h <= 16:   # Europe session
            session_multiplier[i_bar] = 1.3
        elif 0 <= h <= 8:    # Asia session
            session_multiplier[i_bar] = 0.8
        else:
            session_multiplier[i_bar] = 0.6

    # Volume correlates with absolute returns and volatility
    abs_returns = np.abs(np.log(close_prices / open_prices))
    vol_component = abs_returns / (np.mean(abs_returns) + 1e-10) * 0.3

    base_volume = 500.0  # Base BTC volume per 15-min bar
    noise = np.abs(np.random.lognormal(0, 0.6, n_bars))

    volume = base_volume * session_multiplier * (1 + vol_component) * noise

    # Volume spikes on jumps/large moves
    large_moves = abs_returns > np.percentile(abs_returns, 95)
    volume[large_moves] *= np.random.uniform(2, 5, large_moves.sum())

    # Quote volume (volume * typical price)
    typical_price = (high_prices + low_prices + close_prices) / 3
    quote_volume = volume * typical_price

    # Trades count (correlated with volume)
    trades = (volume * np.random.uniform(80, 200, n_bars)).astype(int)

    # Taker buy volume (~45-55% of total, with directional bias)
    returns = np.log(close_prices / open_prices)
    buy_ratio = 0.5 + 0.15 * np.tanh(returns / np.std(returns) * 2)
    taker_buy_base = volume * buy_ratio
    taker_buy_quote = taker_buy_base * typical_price

    # --- Assemble DataFrame ---
    df = pd.DataFrame({
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volume,
        'close_time': timestamps + pd.Timedelta(minutes=interval_minutes),
        'quote_volume': quote_volume,
        'trades': trades,
        'taker_buy_base': taker_buy_base,
        'taker_buy_quote': taker_buy_quote,
    }, index=timestamps)

    df.index.name = 'timestamp'

    return df


def load_or_generate_data(use_api=False, **kwargs):
    """
    Main entry point: tries Binance API first, falls back to synthetic.
    """
    if use_api:
        try:
            print("Attempting to fetch from Binance API...")
            df = fetch_binance_klines(**kwargs)
            print(f"Fetched {len(df)} bars from Binance")
            return df, 'binance_api'
        except Exception as e:
            print(f"Binance API failed: {e}")
            print("Falling back to synthetic data generation...")

    print("Generating synthetic BTC/USDT data...")
    df = generate_synthetic_btcusdt(
        start_date=kwargs.get('start_date', '2021-01-01'),
        end_date=kwargs.get('end_date', '2025-01-01'),
        interval_minutes=kwargs.get('interval_minutes', 15),
        seed=kwargs.get('seed', 42)
    )
    print(f"Generated {len(df)} synthetic bars from {df.index[0]} to {df.index[-1]}")
    return df, 'synthetic'


if __name__ == '__main__':
    df, source = load_or_generate_data()
    print(f"\nData source: {source}")
    print(f"Shape: {df.shape}")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    print(f"\nPrice stats:")
    print(df[['open','high','low','close']].describe())
    print(f"\nVolume stats:")
    print(df[['volume','trades']].describe())
