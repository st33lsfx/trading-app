"""
Indicators Module
==================
Core technical indicators:
- VWAP (daily/session-anchored) with standard deviation bands
- Volume Profile (POC, VAH, VAL, HVN/LVN detection)
- ATR (for volatility-based stops and sizing)
- Volume momentum and delta
"""

import numpy as np
import pandas as pd


# =============================================================================
# VWAP Calculations
# =============================================================================

def compute_vwap(df, anchor='D'):
    """
    Compute anchored VWAP with ±1σ and ±2σ deviation bands.

    Parameters
    ----------
    df : DataFrame with 'high', 'low', 'close', 'volume' columns
    anchor : str
        Resampling anchor for VWAP reset.
        'D' = daily, 'W' = weekly, 'M' = monthly

    Returns
    -------
    DataFrame with vwap, vwap_upper1, vwap_lower1, vwap_upper2, vwap_lower2
    """
    typical_price = (df['high'] + df['low'] + df['close']) / 3.0
    tp_vol = typical_price * df['volume']

    # Create anchor groups (daily by default)
    if anchor == 'D':
        groups = df.index.date
    elif anchor == 'W':
        groups = df.index.isocalendar().week.values
    elif anchor == 'M':
        groups = df.index.to_period('M')
    else:
        groups = df.index.date

    result = pd.DataFrame(index=df.index)
    result['vwap'] = np.nan
    result['vwap_upper1'] = np.nan
    result['vwap_lower1'] = np.nan
    result['vwap_upper2'] = np.nan
    result['vwap_lower2'] = np.nan
    result['vwap_slope'] = np.nan

    unique_groups = pd.Series(groups).unique()

    for group in unique_groups:
        mask = groups == group
        idx = df.index[mask]

        if len(idx) == 0:
            continue

        cum_tp_vol = tp_vol.loc[idx].cumsum()
        cum_vol = df['volume'].loc[idx].cumsum()

        vwap = cum_tp_vol / cum_vol.replace(0, np.nan)

        # Standard deviation bands
        squared_diff = ((typical_price.loc[idx] - vwap) ** 2 * df['volume'].loc[idx])
        cum_sq_diff = squared_diff.cumsum()
        variance = cum_sq_diff / cum_vol.replace(0, np.nan)
        std_dev = np.sqrt(variance.clip(lower=0))

        result.loc[idx, 'vwap'] = vwap.values
        result.loc[idx, 'vwap_upper1'] = (vwap + 1.0 * std_dev).values
        result.loc[idx, 'vwap_lower1'] = (vwap - 1.0 * std_dev).values
        result.loc[idx, 'vwap_upper2'] = (vwap + 2.0 * std_dev).values
        result.loc[idx, 'vwap_lower2'] = (vwap - 2.0 * std_dev).values

    # VWAP slope (rate of change over N bars)
    result['vwap_slope'] = result['vwap'].pct_change(periods=4)

    return result


def compute_multi_timeframe_vwap(df):
    """
    Compute VWAP on daily AND weekly anchors for confluence.
    """
    daily_vwap = compute_vwap(df, anchor='D')
    daily_vwap.columns = [f'daily_{c}' for c in daily_vwap.columns]

    weekly_vwap = compute_vwap(df, anchor='W')
    weekly_vwap.columns = [f'weekly_{c}' for c in weekly_vwap.columns]

    return pd.concat([daily_vwap, weekly_vwap], axis=1)


# =============================================================================
# Volume Profile Calculations
# =============================================================================

def compute_volume_profile(df, lookback_bars=96, n_bins=50):
    """
    Compute rolling Volume Profile metrics for each bar.

    For each bar, looks back `lookback_bars` (default 96 = 1 day of 15-min)
    and computes:
    - POC (Point of Control): price level with highest volume
    - VAH (Value Area High): upper bound of 70% value area
    - VAL (Value Area Low): lower bound of 70% value area
    - HVN flags (High Volume Nodes near price)
    - LVN flags (Low Volume Nodes near price)

    Parameters
    ----------
    df : DataFrame with OHLCV data
    lookback_bars : int, bars to include in profile
    n_bins : int, number of price bins for the profile

    Returns
    -------
    DataFrame with poc, vah, val, hvn_proximity, lvn_proximity
    """
    n = len(df)
    result = pd.DataFrame(index=df.index)
    result['poc'] = np.nan
    result['vah'] = np.nan
    result['val'] = np.nan
    result['hvn_proximity'] = 0.0
    result['lvn_proximity'] = 0.0
    result['profile_width'] = np.nan

    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    volume = df['volume'].values

    for i in range(lookback_bars, n):
        start_idx = i - lookback_bars
        end_idx = i + 1

        # Price range for this profile window
        window_high = high[start_idx:end_idx]
        window_low = low[start_idx:end_idx]
        window_close = close[start_idx:end_idx]
        window_vol = volume[start_idx:end_idx]

        price_min = window_low.min()
        price_max = window_high.max()

        if price_max <= price_min:
            continue

        # Create price bins
        bin_edges = np.linspace(price_min, price_max, n_bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bin_volumes = np.zeros(n_bins)

        # Distribute volume across bins using typical price
        for j in range(lookback_bars + 1):
            tp = (window_high[j] + window_low[j] + window_close[j]) / 3.0
            bin_idx = int((tp - price_min) / (price_max - price_min) * (n_bins - 1))
            bin_idx = max(0, min(n_bins - 1, bin_idx))

            # Also spread volume across the bar's range
            bar_low_bin = int((window_low[j] - price_min) / (price_max - price_min) * (n_bins - 1))
            bar_high_bin = int((window_high[j] - price_min) / (price_max - price_min) * (n_bins - 1))
            bar_low_bin = max(0, min(n_bins - 1, bar_low_bin))
            bar_high_bin = max(0, min(n_bins - 1, bar_high_bin))

            if bar_high_bin > bar_low_bin:
                spread_vol = window_vol[j] / (bar_high_bin - bar_low_bin + 1)
                bin_volumes[bar_low_bin:bar_high_bin + 1] += spread_vol
            else:
                bin_volumes[bin_idx] += window_vol[j]

        # POC: bin with highest volume
        poc_idx = np.argmax(bin_volumes)
        poc_price = bin_centers[poc_idx]

        # Value Area (70% of total volume around POC)
        total_vol = bin_volumes.sum()
        if total_vol <= 0:
            continue

        target_vol = total_vol * 0.70
        va_vol = bin_volumes[poc_idx]
        va_low_idx = poc_idx
        va_high_idx = poc_idx

        while va_vol < target_vol:
            # Expand in direction of higher volume
            expand_up = bin_volumes[va_high_idx + 1] if va_high_idx + 1 < n_bins else 0
            expand_down = bin_volumes[va_low_idx - 1] if va_low_idx - 1 >= 0 else 0

            if expand_up >= expand_down and va_high_idx + 1 < n_bins:
                va_high_idx += 1
                va_vol += bin_volumes[va_high_idx]
            elif va_low_idx - 1 >= 0:
                va_low_idx -= 1
                va_vol += bin_volumes[va_low_idx]
            else:
                break

        vah_price = bin_centers[va_high_idx]
        val_price = bin_centers[va_low_idx]

        result.iloc[i, result.columns.get_loc('poc')] = poc_price
        result.iloc[i, result.columns.get_loc('vah')] = vah_price
        result.iloc[i, result.columns.get_loc('val')] = val_price
        result.iloc[i, result.columns.get_loc('profile_width')] = vah_price - val_price

        # HVN/LVN proximity (is current price near a high/low volume node?)
        current_price = close[i]
        price_range = price_max - price_min
        proximity_threshold = 0.01  # 1% of range

        # Find HVNs (top 20% of volume bins)
        vol_threshold_high = np.percentile(bin_volumes, 80)
        vol_threshold_low = np.percentile(bin_volumes, 20)

        hvn_bins = bin_centers[bin_volumes >= vol_threshold_high]
        lvn_bins = bin_centers[bin_volumes <= vol_threshold_low]

        # HVN proximity score (0 to 1, higher = closer to HVN)
        if len(hvn_bins) > 0:
            min_hvn_dist = np.min(np.abs(hvn_bins - current_price)) / price_range
            result.iloc[i, result.columns.get_loc('hvn_proximity')] = max(0, 1 - min_hvn_dist / proximity_threshold)

        # LVN proximity score
        if len(lvn_bins) > 0:
            min_lvn_dist = np.min(np.abs(lvn_bins - current_price)) / price_range
            result.iloc[i, result.columns.get_loc('lvn_proximity')] = max(0, 1 - min_lvn_dist / proximity_threshold)

    return result


def compute_session_volume_profile(df, session_hours=24, n_bins=50):
    """
    Compute Volume Profile for the PREVIOUS trading session.
    Provides prior session's POC/VAH/VAL as support/resistance.
    """
    # Group by date for session profiles
    df_copy = df.copy()
    df_copy['date'] = df_copy.index.date

    session_profiles = {}
    dates = df_copy['date'].unique()

    for i, date in enumerate(dates):
        if i == 0:
            continue

        prev_date = dates[i - 1]
        prev_mask = df_copy['date'] == prev_date
        prev_data = df_copy[prev_mask]

        if len(prev_data) < 10:
            continue

        # Compute profile for previous session
        price_min = prev_data['low'].min()
        price_max = prev_data['high'].max()

        if price_max <= price_min:
            continue

        bin_edges = np.linspace(price_min, price_max, n_bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bin_volumes = np.zeros(n_bins)

        for _, row in prev_data.iterrows():
            tp = (row['high'] + row['low'] + row['close']) / 3.0
            bin_idx = int((tp - price_min) / (price_max - price_min) * (n_bins - 1))
            bin_idx = max(0, min(n_bins - 1, bin_idx))
            bin_volumes[bin_idx] += row['volume']

        poc_idx = np.argmax(bin_volumes)

        session_profiles[date] = {
            'prev_poc': bin_centers[poc_idx],
            'prev_session_high': price_max,
            'prev_session_low': price_min,
        }

    # Map back to DataFrame
    result = pd.DataFrame(index=df.index)
    result['prev_poc'] = np.nan
    result['prev_session_high'] = np.nan
    result['prev_session_low'] = np.nan

    for idx in df.index:
        date = idx.date()
        if date in session_profiles:
            for col, val in session_profiles[date].items():
                result.loc[idx, col] = val

    return result


# =============================================================================
# Supporting Indicators
# =============================================================================

def compute_atr(df, period=14):
    """Average True Range for volatility measurement."""
    high = df['high']
    low = df['low']
    close = df['close']

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(span=period, adjust=False).mean()

    return atr


def compute_volume_metrics(df, fast_period=10, slow_period=50):
    """
    Volume-based metrics:
    - Relative volume (vs moving average)
    - Volume momentum
    - Buy/sell pressure (taker buy ratio)
    - Volume delta estimate
    """
    result = pd.DataFrame(index=df.index)

    # Relative volume
    vol_sma = df['volume'].rolling(slow_period).mean()
    result['rel_volume'] = df['volume'] / vol_sma.replace(0, np.nan)

    # Volume momentum (fast vs slow MA)
    vol_fast = df['volume'].rolling(fast_period).mean()
    vol_slow = df['volume'].rolling(slow_period).mean()
    result['vol_momentum'] = vol_fast / vol_slow.replace(0, np.nan)

    # Buy pressure from taker data (if available)
    if 'taker_buy_base' in df.columns:
        result['buy_ratio'] = df['taker_buy_base'] / df['volume'].replace(0, np.nan)
        result['volume_delta'] = (2 * df['taker_buy_base'] - df['volume'])
        result['cum_delta'] = result['volume_delta'].cumsum()
        result['delta_ma'] = result['volume_delta'].rolling(fast_period).mean()
    else:
        # Estimate from price action
        body = df['close'] - df['open']
        range_ = df['high'] - df['low']
        result['buy_ratio'] = 0.5 + 0.5 * (body / range_.replace(0, np.nan)).clip(-1, 1)
        result['volume_delta'] = df['volume'] * (result['buy_ratio'] - 0.5) * 2
        result['cum_delta'] = result['volume_delta'].cumsum()
        result['delta_ma'] = result['volume_delta'].rolling(fast_period).mean()

    return result


def compute_momentum(df, rsi_period=14, ma_fast=20, ma_slow=50):
    """
    Momentum indicators for trend confirmation:
    - RSI
    - EMA crossover signal
    - Price momentum (ROC)
    """
    result = pd.DataFrame(index=df.index)
    close = df['close']

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.ewm(span=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(span=rsi_period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result['rsi'] = 100 - (100 / (1 + rs))

    # EMA trend
    result['ema_fast'] = close.ewm(span=ma_fast, adjust=False).mean()
    result['ema_slow'] = close.ewm(span=ma_slow, adjust=False).mean()
    result['ema_signal'] = np.where(result['ema_fast'] > result['ema_slow'], 1, -1)

    # Rate of change
    result['roc'] = close.pct_change(periods=12)

    return result


def compute_all_indicators(df, vp_lookback=96, vp_bins=50,
                           atr_period=14, vol_fast=10, vol_slow=50):
    """
    Master function: compute ALL indicators and merge into single DataFrame.
    """
    print("  Computing VWAP bands...")
    vwap = compute_multi_timeframe_vwap(df)

    print("  Computing Volume Profile (rolling)...")
    vp = compute_volume_profile(df, lookback_bars=vp_lookback, n_bins=vp_bins)

    print("  Computing session profiles...")
    session = compute_session_volume_profile(df, n_bins=vp_bins)

    print("  Computing ATR...")
    atr = compute_atr(df, period=atr_period)

    print("  Computing volume metrics...")
    vol = compute_volume_metrics(df, fast_period=vol_fast, slow_period=vol_slow)

    print("  Computing momentum...")
    mom = compute_momentum(df)

    # Merge all
    result = df.copy()
    result = pd.concat([result, vwap, vp, session, vol, mom], axis=1)
    result['atr'] = atr

    # Derived features for strategy
    result['price_vs_vwap'] = (result['close'] - result['daily_vwap']) / result['atr'].replace(0, np.nan)
    result['price_vs_poc'] = (result['close'] - result['poc']) / result['atr'].replace(0, np.nan)
    result['price_vs_vah'] = (result['close'] - result['vah']) / result['atr'].replace(0, np.nan)
    result['price_vs_val'] = (result['close'] - result['val']) / result['atr'].replace(0, np.nan)

    # VWAP band position (0=at lower2, 0.5=at VWAP, 1=at upper2)
    vwap_range = result['daily_vwap_upper2'] - result['daily_vwap_lower2']
    result['vwap_position'] = (result['close'] - result['daily_vwap_lower2']) / vwap_range.replace(0, np.nan)
    result['vwap_position'] = result['vwap_position'].clip(0, 1)

    return result
