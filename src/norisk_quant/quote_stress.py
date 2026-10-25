"""QS01 frozen quote-stress hypothesis; design screening, not live execution.

Rules are fixed in docs/PRE_REGISTERED_QS01_QUOTE_STRESS_2026-10-25.md.
Bid/Ask spread is a predictor only. Execution uses the central synthetic BID
reference and exactly $0.40/oz roundtrip, with no additional spread charge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .model import Settings, Signal

STRATEGY = "QS01_quote_stress_exhaustion_frozen"


def qs01_settings() -> Settings:
    """Exact next-minute open, one ounce, 30 elapsed-minute holding cap."""
    return Settings(
        ounces=1.0, roundtrip_cost_per_ounce=0.40,
        max_entry_delay_minutes=0, max_holding_minutes=30,
    )


def quote_stress_features(minutes: pd.DataFrame) -> pd.DataFrame:
    """Causal features at each minute CLOSE; no future-row filtering.

    Wilder ATR is SMA-seeded from the first 20 true ranges with a previous
    contiguous close, then recursively smoothed with alpha=1/20. Reset after
    gaps: a gap-spanning true range cannot seed a contiguous-minute signal.
    The t row only uses the ATR at t-1. Initial seeding is exposed explicitly
    because the preregistration names Wilder ATR without its seed convention.
    """
    if not isinstance(minutes.index, pd.DatetimeIndex) or minutes.index.tz is None:
        raise ValueError("QS01 requires timezone-aware M1 dates")
    if minutes.index.has_duplicates or not minutes.index.is_monotonic_increasing:
        raise ValueError("QS01 dates must be sorted and unique")
    if (minutes.index.asi8 % 60_000_000_000 != 0).any():
        raise ValueError("QS01 candle opens must align to minute boundaries")
    required = ["o", "h", "l", "c", "ac"]
    if not set(required).issubset(minutes):
        raise ValueError("QS01 requires BID OHLC and ASK close")
    values = minutes[required].to_numpy(dtype=float)
    if not np.isfinite(values[:, :4]).all():
        raise ValueError("QS01 requires finite BID OHLC")
    if len(minutes) == 0:
        return pd.DataFrame(index=minutes.index, columns=[
            "spread", "prior_spread_median_240", "prior_wilder_atr20",
            "displacement", "contiguous_history", "side", "stop_distance",
        ])
    op, hi, lo, cl, ask_close = values.T
    if (lo <= 0).any() or (lo > np.minimum(op, cl)).any() or (hi < np.maximum(op, cl)).any():
        raise ValueError("Invalid BID OHLC")
    count = len(minutes)
    run_length = np.ones(count, dtype=np.int64)
    atr = np.full(count, np.nan)
    stamps = minutes.index.asi8
    seed_total = 0.0
    seed_count = 0
    current_atr = np.nan
    for i in range(1, count):
        if stamps[i] - stamps[i - 1] != 60_000_000_000:
            seed_total = 0.0
            seed_count = 0
            current_atr = np.nan
            continue
        run_length[i] = run_length[i - 1] + 1
        tr = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
        if seed_count < 20:
            seed_total += tr
            seed_count += 1
            if seed_count == 20:
                current_atr = seed_total / 20
        else:
            current_atr = (current_atr * 19 + tr) / 20
        atr[i] = current_atr
    spread = pd.Series(ask_close - cl, index=minutes.index)
    median = spread.shift(1).rolling(240, min_periods=240).median()
    prior_atr = pd.Series(atr, index=minutes.index).shift(1)
    displacement = minutes["c"].diff()
    valid = (
        (run_length >= 241) & np.isfinite(spread) & (spread >= 0)
        & np.isfinite(median) & (median > 0)
        & (prior_atr > 0) & np.isfinite(prior_atr)
        & (spread >= 2.5 * median) & (spread <= 3.00)
        & (displacement.abs() >= 1.5 * prior_atr) & (displacement != 0)
    )
    side = pd.Series(np.where(valid, -np.sign(displacement), 0), index=minutes.index, dtype=int)
    return pd.DataFrame({
        "spread": spread,
        "prior_spread_median_240": median,
        "prior_wilder_atr20": prior_atr,
        "displacement": displacement,
        "contiguous_history": run_length >= 241,
        "side": side,
        "stop_distance": 1.5 * prior_atr,
    })


def quote_stress_signals(minutes: pd.DataFrame) -> list[Signal]:
    """Emit frozen signals without examining whether a next quote exists."""
    features = quote_stress_features(minutes)
    signals = []
    for at, feature in features.loc[features["side"] != 0].iterrows():
        distance = float(feature["stop_distance"])
        signals.append(Signal(
            confirmed_at=at + pd.Timedelta(minutes=1),
            side=int(feature["side"]), stop_distance=distance,
            target_distance=distance, strategy=STRATEGY,
        ))
    return signals
