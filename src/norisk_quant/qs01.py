"""Frozen QS01 M1 quote-stress exhaustion signal generator.

The ask-minus-bid CLOSE spread is a predictor only. It is never charged as
an extra execution cost. No future minute is read to construct a signal.
This module does not infer intraminute tick order or broker execution.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .model import Signal
from .quote_stress import STRATEGY, quote_stress_signals


QS01_STRATEGY = STRATEGY


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

    # Preserve the public module/API and its strict importer-facing guards,
    # while sharing the exact signal implementation used in the audited
    # frozen design run. Do not maintain a second ATR/threshold algorithm.
    return quote_stress_signals(m1)
