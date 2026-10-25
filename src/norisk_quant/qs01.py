"""Frozen QS01 M1 quote-stress exhaustion signal generator.

The ask-minus-bid CLOSE spread is a predictor only. It is never charged as
an extra execution cost. No future minute is read to construct a signal.
This module does not infer intraminute tick order or broker execution.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .model import Signal


QS01_STRATEGY = "QS01_quote_stress_exhaustion"


def qs01_signals(m1: pd.DataFrame) -> list[Signal]:
    """Apply the 2026-10-25 frozen QS01 rules without parameter search.

    Execution contract: reference/fast M1 engine, entry_delay=0 minutes,
    max_hold=30 elapsed UTC minutes, 1 oz, $0.40 all-in roundtrip.
    """
    if not isinstance(m1.index, pd.DatetimeIndex) or m1.index.tz is None:
        raise ValueError("QS01 requires timezone-aware M1 DatetimeIndex")
    if m1.index.has_duplicates or not m1.index.is_monotonic_increasing:
        raise ValueError("QS01 requires sorted unique M1 timestamps")
    if (m1.index.asi8 % 60_000_000_000 != 0).any():
        raise ValueError("QS01 requires minute-open timestamps")
    required = ("o", "h", "l", "c", "ao", "ah", "al", "ac")
    if not set(required).issubset(m1.columns):
        raise ValueError("QS01 requires original Bid/Ask OHLC columns")
    if m1.empty:
        return []
    prices = m1.loc[:, required].to_numpy(dtype=np.float64)
    if not np.isfinite(prices).all():
        raise ValueError("QS01 requires finite Bid/Ask OHLC")
    o, h, l, c, ao, ah, al, ac = prices.T
    if (
        (l <= 0).any() or (al <= 0).any()
        or (l > np.minimum(o, c)).any()
        or (h < np.maximum(o, c)).any()
        or (al > np.minimum(ao, ac)).any()
        or (ah < np.maximum(ao, ac)).any()
        or (ao < o).any() or (ac < c).any()
    ):
        raise ValueError("QS01 invalid Bid/Ask OHLC or crossed quotes")

    n = len(m1)
    if n < 241:
        return []
    stamps = m1.index.asi8
    contiguous = np.ones(n, dtype=np.int32)
    atr = np.full(n, np.nan, dtype=np.float64)
    tr = np.full(n, np.nan, dtype=np.float64)
    # Reset Wilder ATR at every missing M1 interval. Twenty TR observations
    # require 21 consecutive candles. Current candle TR is never used to
    # estimate the current signal's stop or target.
    for i in range(1, n):
        if stamps[i] - stamps[i - 1] != 60_000_000_000:
            continue
        contiguous[i] = contiguous[i - 1] + 1
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if contiguous[i] == 21:
            atr[i] = float(np.mean(tr[i - 19:i + 1]))
        elif contiguous[i] > 21:
            atr[i] = (atr[i - 1] * 19.0 + tr[i]) / 20.0

    spread = ac - c
    spread_valid = np.isfinite(spread) & (spread >= 0)
    prior_spread = pd.Series(spread).shift(1)
    baseline = prior_spread.rolling(240, min_periods=240).median().to_numpy()
    prior_valid = (
        pd.Series(spread_valid.astype(np.int16)).shift(1)
        .rolling(240, min_periods=240).sum().to_numpy() == 240
    )
    prior_atr = np.empty(n, dtype=np.float64)
    prior_atr[0] = np.nan
    prior_atr[1:] = atr[:-1]
    delta = np.empty(n, dtype=np.float64)
    delta[0] = np.nan
    delta[1:] = c[1:] - c[:-1]
    qualified = (
        (contiguous >= 241) & prior_valid
        & (baseline > 0) & (spread >= 2.5 * baseline)
        & (spread <= 3.0) & (prior_atr > 0)
        & (np.abs(delta) >= 1.5 * prior_atr)
        & (delta != 0)
    )
    return [
        Signal(
            confirmed_at=m1.index[int(i)] + pd.Timedelta(minutes=1),
            side=-1 if delta[i] > 0 else 1,
            stop_distance=float(1.5 * prior_atr[i]),
            target_distance=float(1.5 * prior_atr[i]),
            strategy=QS01_STRATEGY,
        )
        for i in np.flatnonzero(qualified)
    ]
