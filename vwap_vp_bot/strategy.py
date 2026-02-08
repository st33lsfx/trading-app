"""
Strategy Module — Hybrid VWAP + Volume Profile Confluence
==========================================================

Implements a score-based signal system that combines:
1. VWAP Mean Reversion: Trade bounces off VWAP deviation bands
2. Volume Profile S/R: POC, VAH, VAL as dynamic support/resistance
3. Volume Confirmation: Only enter on volume spikes / delta confirmation
4. Adaptive regime detection: Switch between mean-reversion and breakout modes

Signal Generation:
- Scores from -100 (strong short) to +100 (strong long)
- Entry threshold is adaptive (set by walk-forward optimization)
- Multiple sub-signals combine for confluence

All parameters are exposed for walk-forward optimization.
"""

import numpy as np
import pandas as pd


class StrategyParams:
    """
    All tunable strategy parameters.
    Defaults are reasonable starting points; walk-forward will optimize.
    """
    def __init__(self, **kwargs):
        # --- Signal thresholds ---
        self.entry_score_long = kwargs.get('entry_score_long', 45)
        self.entry_score_short = kwargs.get('entry_score_short', -45)
        self.exit_score_long = kwargs.get('exit_score_long', -10)
        self.exit_score_short = kwargs.get('exit_score_short', 10)

        # --- VWAP mean reversion weights ---
        self.vwap_mr_weight = kwargs.get('vwap_mr_weight', 30)
        self.vwap_band_entry = kwargs.get('vwap_band_entry', 1.0)  # Enter at ±Nσ from VWAP
        self.vwap_slope_filter = kwargs.get('vwap_slope_filter', 0.0002)  # Min slope for trend

        # --- Volume Profile weights ---
        self.vp_weight = kwargs.get('vp_weight', 25)
        self.poc_proximity = kwargs.get('poc_proximity', 0.5)  # ATR units for "near POC"
        self.va_breakout_confirm = kwargs.get('va_breakout_confirm', 1.2)  # Vol ratio for breakout

        # --- Volume confirmation ---
        self.vol_weight = kwargs.get('vol_weight', 20)
        self.min_rel_volume = kwargs.get('min_rel_volume', 1.0)  # Min relative vol for entry
        self.delta_weight = kwargs.get('delta_weight', 15)

        # --- Momentum filter ---
        self.momentum_weight = kwargs.get('momentum_weight', 10)
        self.rsi_oversold = kwargs.get('rsi_oversold', 35)
        self.rsi_overbought = kwargs.get('rsi_overbought', 65)

        # --- Regime detection ---
        self.regime_lookback = kwargs.get('regime_lookback', 48)  # Bars for regime detection
        self.trend_atr_threshold = kwargs.get('trend_atr_threshold', 1.5)  # ATR multiplier for trend

        # --- Volume Profile lookback ---
        self.vp_lookback = kwargs.get('vp_lookback', 96)  # Bars for VP calculation

        # --- Cooldown ---
        self.min_bars_between_trades = kwargs.get('min_bars_between_trades', 4)

    def to_dict(self):
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


# Parameter search space for walk-forward optimization
PARAM_GRID = {
    'entry_score_long': [35, 40, 45, 50, 55],
    'entry_score_short': [-55, -50, -45, -40, -35],
    'vwap_mr_weight': [20, 25, 30, 35],
    'vp_weight': [15, 20, 25, 30],
    'vol_weight': [15, 20, 25],
    'vwap_band_entry': [0.8, 1.0, 1.2],
    'min_rel_volume': [0.8, 1.0, 1.2, 1.5],
    'rsi_oversold': [30, 35],
    'rsi_overbought': [65, 70],
    'vp_lookback': [64, 96, 128],
}

# Reduced grid for faster optimization
PARAM_GRID_FAST = {
    'entry_score_long': [40, 45, 50],
    'entry_score_short': [-50, -45, -40],
    'vwap_mr_weight': [25, 30, 35],
    'vp_weight': [20, 25],
    'min_rel_volume': [0.8, 1.0, 1.2],
}


def detect_regime(df, lookback=48):
    """
    Classify market regime: trending vs ranging.

    Uses ADX-like directional movement and volatility expansion.

    Returns
    -------
    Series: 'trending_up', 'trending_down', or 'ranging'
    """
    close = df['close']
    atr = df['atr'] if 'atr' in df.columns else (df['high'] - df['low']).rolling(14).mean()

    # Price displacement over lookback
    displacement = close - close.shift(lookback)
    atr_ma = atr.rolling(lookback).mean()

    # Displacement relative to volatility
    disp_ratio = displacement / (atr_ma * np.sqrt(lookback)).replace(0, np.nan)

    regimes = pd.Series('ranging', index=df.index)
    regimes[disp_ratio > 1.0] = 'trending_up'
    regimes[disp_ratio < -1.0] = 'trending_down'

    return regimes


def compute_vwap_score(row, params):
    """
    Score based on VWAP position and bands.

    Mean Reversion Logic:
    - Price at/below lower band → long signal (positive score)
    - Price at/above upper band → short signal (negative score)
    - VWAP slope confirms or filters

    Breakout Logic (when trending):
    - Price above VWAP with positive slope → long confirmation
    """
    score = 0.0

    vwap_pos = row.get('vwap_position', 0.5)
    vwap_slope = row.get('daily_vwap_slope', 0)
    price_vs_vwap = row.get('price_vs_vwap', 0)

    if pd.isna(vwap_pos) or pd.isna(price_vs_vwap):
        return 0.0

    # Mean reversion component
    # Price below VWAP lower1 → bullish
    if price_vs_vwap < -params.vwap_band_entry:
        score += params.vwap_mr_weight * min(abs(price_vs_vwap) / 2.0, 1.5)
    # Price above VWAP upper1 → bearish
    elif price_vs_vwap > params.vwap_band_entry:
        score -= params.vwap_mr_weight * min(abs(price_vs_vwap) / 2.0, 1.5)

    # Trend confirmation via slope
    if not pd.isna(vwap_slope):
        if vwap_slope > params.vwap_slope_filter:
            score += 5  # Bullish bias
        elif vwap_slope < -params.vwap_slope_filter:
            score -= 5  # Bearish bias

    # Weekly VWAP confluence
    weekly_vwap_pos = row.get('price_vs_vwap', 0)
    if not pd.isna(row.get('weekly_vwap', np.nan)):
        weekly_diff = (row['close'] - row['weekly_vwap']) / row.get('atr', 1)
        if abs(weekly_diff) < 0.5:  # Near weekly VWAP = confluence
            score *= 1.2  # Amplify signal at weekly VWAP

    return np.clip(score, -50, 50)


def compute_vp_score(row, params, regime='ranging'):
    """
    Score based on Volume Profile levels.

    - Near POC in ranging market → mean reversion potential
    - Breaking above VAH with volume → bullish breakout
    - Breaking below VAL with volume → bearish breakout
    - Near previous session POC → S/R
    """
    score = 0.0

    price_vs_poc = row.get('price_vs_poc', 0)
    price_vs_vah = row.get('price_vs_vah', 0)
    price_vs_val = row.get('price_vs_val', 0)
    rel_volume = row.get('rel_volume', 1.0)

    if pd.isna(price_vs_poc):
        return 0.0

    if regime == 'ranging':
        # Mean reversion around POC
        if abs(price_vs_poc) < params.poc_proximity:
            # At POC → neutral, waiting for direction
            score += 0
        elif price_vs_val < -0.3:
            # Below VAL in range → potential long (buy at support)
            score += params.vp_weight * 0.6
        elif price_vs_vah > 0.3:
            # Above VAH in range → potential short (sell at resistance)
            score -= params.vp_weight * 0.6
        # Price between VAL and POC → mild bullish
        elif price_vs_val > 0 and price_vs_poc < 0:
            score += params.vp_weight * 0.3
        # Price between POC and VAH → mild bearish
        elif price_vs_poc > 0 and price_vs_vah < 0:
            score -= params.vp_weight * 0.3

    else:  # Trending
        # Breakout confirmation
        if price_vs_vah > 0.5 and rel_volume > params.va_breakout_confirm:
            score += params.vp_weight * 0.8  # Bullish breakout
        elif price_vs_val < -0.5 and rel_volume > params.va_breakout_confirm:
            score -= params.vp_weight * 0.8  # Bearish breakout

        # Pullback to POC in trend → continuation
        if regime == 'trending_up' and abs(price_vs_poc) < params.poc_proximity:
            score += params.vp_weight * 0.4
        elif regime == 'trending_down' and abs(price_vs_poc) < params.poc_proximity:
            score -= params.vp_weight * 0.4

    # Previous session POC as S/R
    prev_poc = row.get('prev_poc', np.nan)
    if not pd.isna(prev_poc):
        atr = row.get('atr', 1)
        prev_poc_dist = (row['close'] - prev_poc) / atr if atr > 0 else 0

        if abs(prev_poc_dist) < 0.3:
            # Near previous POC → expect reaction
            if prev_poc_dist > 0:
                score -= 3  # Potential resistance
            else:
                score += 3  # Potential support

    return np.clip(score, -40, 40)


def compute_volume_score(row, params):
    """
    Volume confirmation score.
    - High relative volume confirms moves
    - Volume delta shows buying/selling pressure
    - Low volume = weak signal, reduce score
    """
    score = 0.0

    rel_vol = row.get('rel_volume', 1.0)
    buy_ratio = row.get('buy_ratio', 0.5)
    delta_ma = row.get('delta_ma', 0)
    vol_momentum = row.get('vol_momentum', 1.0)

    if pd.isna(rel_vol):
        return 0.0

    # Volume filter: require minimum volume
    if rel_vol < params.min_rel_volume:
        return -5  # Negative score for low volume = suppress signals

    # Volume delta direction
    if not pd.isna(delta_ma) and delta_ma != 0:
        delta_norm = np.clip(delta_ma / (abs(delta_ma) + 1e-10), -1, 1)
        score += params.delta_weight * delta_norm * 0.5

    # Buy/sell pressure
    if not pd.isna(buy_ratio):
        pressure = (buy_ratio - 0.5) * 2  # -1 to +1
        score += params.vol_weight * pressure * 0.3

    # Volume expansion → confirms breakout
    if vol_momentum > 1.3:
        score *= 1.2

    return np.clip(score, -25, 25)


def compute_momentum_score(row, params):
    """
    Momentum filter score using RSI and EMA.
    """
    score = 0.0
    rsi = row.get('rsi', 50)
    ema_signal = row.get('ema_signal', 0)
    roc = row.get('roc', 0)

    if pd.isna(rsi):
        return 0.0

    # RSI extremes
    if rsi < params.rsi_oversold:
        score += params.momentum_weight * (params.rsi_oversold - rsi) / 20.0
    elif rsi > params.rsi_overbought:
        score -= params.momentum_weight * (rsi - params.rsi_overbought) / 20.0

    # EMA trend
    score += ema_signal * params.momentum_weight * 0.2

    # ROC
    if not pd.isna(roc):
        score += np.clip(roc * 100, -5, 5)

    return np.clip(score, -20, 20)


def generate_signals(df, params=None):
    """
    Master signal generator: combines all sub-signals into final score.

    Returns DataFrame with:
    - 'signal_score': composite score (-100 to +100)
    - 'signal': 1 (long), -1 (short), 0 (neutral)
    - 'regime': detected market regime
    - Individual component scores
    """
    if params is None:
        params = StrategyParams()

    # Detect regime
    regimes = detect_regime(df, lookback=params.regime_lookback)

    n = len(df)
    scores = np.zeros(n)
    vwap_scores = np.zeros(n)
    vp_scores = np.zeros(n)
    vol_scores = np.zeros(n)
    mom_scores = np.zeros(n)

    for i in range(n):
        row = df.iloc[i]
        regime = regimes.iloc[i]

        # Component scores
        vwap_s = compute_vwap_score(row, params)
        vp_s = compute_vp_score(row, params, regime)
        vol_s = compute_volume_score(row, params)
        mom_s = compute_momentum_score(row, params)

        # Regime-adaptive weighting
        if regime == 'ranging':
            # Favor mean reversion
            total = vwap_s * 1.2 + vp_s * 1.3 + vol_s * 0.8 + mom_s * 0.7
        else:
            # Favor breakout/trend
            total = vwap_s * 0.7 + vp_s * 1.1 + vol_s * 1.2 + mom_s * 1.0

        scores[i] = total
        vwap_scores[i] = vwap_s
        vp_scores[i] = vp_s
        vol_scores[i] = vol_s
        mom_scores[i] = mom_s

    result = pd.DataFrame(index=df.index)
    result['signal_score'] = np.clip(scores, -100, 100)
    result['vwap_component'] = vwap_scores
    result['vp_component'] = vp_scores
    result['vol_component'] = vol_scores
    result['mom_component'] = mom_scores
    result['regime'] = regimes

    # Generate discrete signals with hysteresis
    signals = np.zeros(n, dtype=int)
    position = 0  # Track current position for hysteresis
    last_trade_bar = -params.min_bars_between_trades

    for i in range(n):
        if i - last_trade_bar < params.min_bars_between_trades:
            signals[i] = position
            continue

        score = result['signal_score'].iloc[i]

        if position == 0:
            if score >= params.entry_score_long:
                position = 1
                last_trade_bar = i
            elif score <= params.entry_score_short:
                position = -1
                last_trade_bar = i
        elif position == 1:
            if score <= params.exit_score_long:
                position = 0
                last_trade_bar = i
            elif score <= params.entry_score_short:
                position = -1
                last_trade_bar = i
        elif position == -1:
            if score >= params.exit_score_short:
                position = 0
                last_trade_bar = i
            elif score >= params.entry_score_long:
                position = 1
                last_trade_bar = i

        signals[i] = position

    result['signal'] = signals

    return result
