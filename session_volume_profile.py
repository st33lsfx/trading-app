"""
Session Volume Profile — Per-session VP with POC, VAH, VAL
===========================================================
Calculates volume profiles for each trading session:
  - Asian  : 00:00–08:00 UTC
  - London : 08:00–13:00 UTC
  - New York: 13:00–21:00 UTC

Provides:
  - Per-session POC / VAH / VAL
  - Composite (all-sessions) profile
  - Previous session carry-over levels
  - VWAP per session with deviation bands
  - Signal scoring based on session VP levels

Uses the same OHLC-distributed volume approach as EliteStrategyV2.
"""

import pandas as pd
import numpy as np
from datetime import datetime, time, timezone


# ═══════════════════════════════════════════════════════════════
# SESSION DEFINITIONS (UTC)
# ═══════════════════════════════════════════════════════════════

SESSIONS = {
    "Asian":    (time(0, 0), time(8, 0)),
    "London":   (time(8, 0), time(13, 0)),
    "New York": (time(13, 0), time(21, 0)),
}

SESSION_COLORS = {
    "Asian":    "#ffdd00",   # yellow
    "London":   "#00f5ff",   # cyan
    "New York": "#ff00aa",   # pink
    "Composite": "#00ff88",  # green
}


def _to_utc(idx):
    """Ensure DatetimeIndex is in UTC."""
    if idx.tz is None:
        return idx.tz_localize("UTC")
    return idx.tz_convert("UTC")


def _assign_session(hour):
    """Return session name based on UTC hour."""
    if 0 <= hour < 8:
        return "Asian"
    elif 8 <= hour < 13:
        return "London"
    elif 13 <= hour < 21:
        return "New York"
    else:
        return "Off-Hours"


# ═══════════════════════════════════════════════════════════════
# VOLUME PROFILE CALCULATION
# ═══════════════════════════════════════════════════════════════

def calculate_volume_profile(df, num_bins=30, value_area_pct=0.70):
    """
    Build a volume profile from OHLCV data.

    Parameters
    ----------
    df : DataFrame with High, Low, Close, Volume columns
    num_bins : int, number of price bins
    value_area_pct : float, percentage of total volume defining value area

    Returns
    -------
    dict with keys: poc, vah, val, bin_centers, bin_volumes, total_volume
    or None if insufficient data.
    """
    if df.empty or len(df) < 2:
        return None

    price_high = df["High"].max()
    price_low = df["Low"].min()
    price_range = price_high - price_low

    if price_range <= 0:
        return None

    bin_edges = np.linspace(price_low, price_high, num_bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    bin_volumes = np.zeros(num_bins)

    for _, row in df.iterrows():
        vol = row.get("Volume", 0)
        if pd.isna(vol) or vol <= 0:
            # Forex proxy: use candle range as volume proxy
            vol = (row["High"] - row["Low"]) * 100_000
        if vol <= 0:
            continue

        lo, hi = row["Low"], row["High"]
        candle_range = hi - lo if hi > lo else 1e-10
        for i in range(num_bins):
            overlap = max(0, min(hi, bin_edges[i + 1]) - max(lo, bin_edges[i]))
            bin_volumes[i] += vol * (overlap / candle_range)

    total_volume = bin_volumes.sum()
    if total_volume <= 0:
        return None

    # POC
    poc_idx = np.argmax(bin_volumes)
    poc = float(bin_centers[poc_idx])

    # Value Area: expand from POC outward
    va_volume = bin_volumes[poc_idx]
    lo_idx, hi_idx = poc_idx, poc_idx

    while va_volume / total_volume < value_area_pct:
        expand_lo = bin_volumes[lo_idx - 1] if lo_idx > 0 else 0
        expand_hi = bin_volumes[hi_idx + 1] if hi_idx < num_bins - 1 else 0

        if expand_hi >= expand_lo and hi_idx < num_bins - 1:
            hi_idx += 1
            va_volume += bin_volumes[hi_idx]
        elif lo_idx > 0:
            lo_idx -= 1
            va_volume += bin_volumes[lo_idx]
        else:
            break

    val = float(bin_centers[lo_idx])
    vah = float(bin_centers[hi_idx])

    return {
        "poc": poc,
        "vah": vah,
        "val": val,
        "bin_centers": bin_centers.tolist(),
        "bin_volumes": bin_volumes.tolist(),
        "total_volume": float(total_volume),
    }


def calculate_session_vwap(df):
    """
    Calculate VWAP + 1σ/2σ bands for a session chunk.

    Returns dict with vwap, upper_1, lower_1, upper_2, lower_2 (single values)
    or None.
    """
    if df.empty or len(df) < 2:
        return None

    has_volume = (df["Volume"] > 0).sum() > len(df) * 0.3
    if has_volume:
        vol = df["Volume"].clip(lower=1)
    else:
        vol = ((df["High"] - df["Low"]).clip(lower=1e-10) * 100_000)

    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_vol = vol.cumsum()
    cum_tp_vol = (tp * vol).cumsum()
    vwap_series = cum_tp_vol / cum_vol

    # Standard deviation bands
    squared_diff = ((tp - vwap_series) ** 2 * vol).cumsum()
    variance = squared_diff / cum_vol
    std = np.sqrt(variance.clip(lower=0))

    last_vwap = float(vwap_series.iloc[-1])
    last_std = float(std.iloc[-1])

    return {
        "vwap": last_vwap,
        "upper_1": last_vwap + last_std,
        "lower_1": last_vwap - last_std,
        "upper_2": last_vwap + 2 * last_std,
        "lower_2": last_vwap - 2 * last_std,
        "vwap_series": vwap_series,
        "std_series": std,
    }


# ═══════════════════════════════════════════════════════════════
# SESSION VOLUME PROFILE ENGINE
# ═══════════════════════════════════════════════════════════════

class SessionVolumeProfile:
    """
    Computes and stores volume profiles per trading session.

    Usage:
        svp = SessionVolumeProfile()
        result = svp.analyze(df)  # df = OHLCV with DatetimeIndex
    """

    def __init__(self, num_bins=30, value_area_pct=0.70):
        self.num_bins = num_bins
        self.value_area_pct = value_area_pct

    def analyze(self, df):
        """
        Analyze OHLCV data and return per-session volume profiles.

        Parameters
        ----------
        df : DataFrame with DatetimeIndex and OHLCV columns

        Returns
        -------
        dict with keys:
            sessions: dict[session_name] -> {profile, vwap_data, candle_count}
            composite: overall volume profile
            previous_sessions: list of completed session profiles (for carry-over)
            current_session: name of current session
            levels: flat list of key levels for strategy use
        """
        if df.empty or len(df) < 5:
            return None

        df = df.copy()
        df.index = _to_utc(df.index)
        df["_utc_hour"] = df.index.hour
        df["_session"] = df["_utc_hour"].apply(_assign_session)
        df["_date"] = df.index.date

        # Current session
        last_hour = df["_utc_hour"].iloc[-1]
        current_session = _assign_session(last_hour)
        current_date = df["_date"].iloc[-1]

        sessions = {}
        previous_sessions = []

        # Group by date + session
        for (dt, sess_name), group in df.groupby(["_date", "_session"]):
            if sess_name == "Off-Hours":
                continue
            if len(group) < 2:
                continue

            profile = calculate_volume_profile(
                group, self.num_bins, self.value_area_pct
            )
            vwap_data = calculate_session_vwap(group)

            entry = {
                "date": dt,
                "session": sess_name,
                "profile": profile,
                "vwap_data": vwap_data,
                "candle_count": len(group),
                "time_start": group.index[0],
                "time_end": group.index[-1],
            }

            # Store under session key (overwrite with latest date)
            sessions[sess_name] = entry

            # Previous sessions = completed sessions (not current)
            is_current = (dt == current_date and sess_name == current_session)
            if not is_current and profile is not None:
                previous_sessions.append(entry)

        # Composite (full dataset)
        composite = calculate_volume_profile(
            df, self.num_bins, self.value_area_pct
        )

        # Flatten key levels for strategy integration
        levels = self._extract_levels(sessions, previous_sessions, composite)

        return {
            "sessions": sessions,
            "composite": composite,
            "previous_sessions": previous_sessions[-6:],  # last 6 completed sessions
            "current_session": current_session,
            "levels": levels,
        }

    def _extract_levels(self, sessions, previous_sessions, composite):
        """
        Extract a flat dict of key price levels for strategy use.
        """
        levels = {}

        # Current session levels
        for name, entry in sessions.items():
            p = entry.get("profile")
            v = entry.get("vwap_data")
            if p:
                prefix = name.lower().replace(" ", "_")
                levels[f"{prefix}_poc"] = p["poc"]
                levels[f"{prefix}_vah"] = p["vah"]
                levels[f"{prefix}_val"] = p["val"]
            if v:
                prefix = name.lower().replace(" ", "_")
                levels[f"{prefix}_vwap"] = v["vwap"]

        # Previous session carry-over (most recent completed session)
        if previous_sessions:
            prev = previous_sessions[-1]
            pp = prev.get("profile")
            if pp:
                levels["prev_session_poc"] = pp["poc"]
                levels["prev_session_vah"] = pp["vah"]
                levels["prev_session_val"] = pp["val"]
                levels["prev_session_name"] = prev["session"]

        # Composite
        if composite:
            levels["composite_poc"] = composite["poc"]
            levels["composite_vah"] = composite["vah"]
            levels["composite_val"] = composite["val"]

        return levels

    def get_signal_score(self, current_price, levels, direction="BUY"):
        """
        Score how well current price aligns with session VP levels.

        Returns (score, reasons) where score is 0-6.
        Higher = stronger confirmation.
        """
        if not levels:
            return 0, []

        score = 0
        reasons = []

        poc = levels.get("composite_poc")
        vah = levels.get("composite_vah")
        val = levels.get("composite_val")
        prev_poc = levels.get("prev_session_poc")

        if poc is None:
            return 0, []

        price_range = (vah - val) if (vah and val and vah > val) else abs(poc * 0.01)
        tolerance = price_range * 0.05  # 5% of value area range

        if direction == "BUY":
            # Price near VAL = good buy zone
            if val and abs(current_price - val) < tolerance:
                score += 2
                reasons.append("Price at Value Area Low (support)")

            # Price above POC = trend confirmation
            if current_price > poc:
                score += 1
                reasons.append("Above POC (bullish)")

            # Price near previous session POC (carry-over support)
            if prev_poc and abs(current_price - prev_poc) < tolerance:
                score += 1
                reasons.append("At prev session POC")

            # Price inside value area
            if val and vah and val <= current_price <= vah:
                score += 1
                reasons.append("Inside Value Area")

        elif direction == "SELL":
            # Price near VAH = good sell zone
            if vah and abs(current_price - vah) < tolerance:
                score += 2
                reasons.append("Price at Value Area High (resistance)")

            # Price below POC = bearish
            if current_price < poc:
                score += 1
                reasons.append("Below POC (bearish)")

            # Price near previous session POC
            if prev_poc and abs(current_price - prev_poc) < tolerance:
                score += 1
                reasons.append("At prev session POC")

            # Price inside value area
            if val and vah and val <= current_price <= vah:
                score += 1
                reasons.append("Inside Value Area")

        return score, reasons


# ═══════════════════════════════════════════════════════════════
# STREAMLIT VISUALIZATION HELPERS
# ═══════════════════════════════════════════════════════════════

def build_session_profile_chart_data(result):
    """
    Convert SessionVolumeProfile result into data suitable for
    Plotly / Streamlit visualization.

    Returns a list of dicts, each representing one session's profile bars.
    """
    if not result:
        return []

    chart_data = []

    for sess_name, entry in result["sessions"].items():
        profile = entry.get("profile")
        if not profile:
            continue

        for center, vol in zip(profile["bin_centers"], profile["bin_volumes"]):
            chart_data.append({
                "price": center,
                "volume": vol,
                "session": sess_name,
                "color": SESSION_COLORS.get(sess_name, "#888888"),
            })

    return chart_data


def build_levels_table(result):
    """
    Build a summary DataFrame of all session levels.
    """
    if not result:
        return pd.DataFrame()

    rows = []

    for sess_name, entry in result["sessions"].items():
        profile = entry.get("profile")
        vwap = entry.get("vwap_data")
        if not profile:
            continue

        row = {
            "Session": sess_name,
            "POC": profile["poc"],
            "VAH": profile["vah"],
            "VAL": profile["val"],
            "VWAP": vwap["vwap"] if vwap else None,
            "VWAP +1σ": vwap["upper_1"] if vwap else None,
            "VWAP -1σ": vwap["lower_1"] if vwap else None,
            "Candles": entry["candle_count"],
        }
        rows.append(row)

    # Composite
    comp = result.get("composite")
    if comp:
        rows.append({
            "Session": "Composite",
            "POC": comp["poc"],
            "VAH": comp["vah"],
            "VAL": comp["val"],
            "VWAP": None,
            "VWAP +1σ": None,
            "VWAP -1σ": None,
            "Candles": sum(e["candle_count"] for e in result["sessions"].values()),
        })

    return pd.DataFrame(rows)
