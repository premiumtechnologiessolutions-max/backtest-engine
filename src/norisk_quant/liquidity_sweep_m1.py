"""Causal M1 prior-range sweep and close-back-inside research signals.

This is an unvalidated hypothesis, NOT investment advice or a fill claim.
Signals are timestamped after the reclaim candle closes. Stops and targets
are distances from the *next observed entry open*, not absolute sweep-wick
prices: a changing open can move both absolute levels.
"""
from __future__ import annotations

import math
from numbers import Integral

import numpy as np
import pandas as pd

from .model import Signal
from .strategy import aggregate_bars


def sweep_reclaim_m1_signals(
    minutes: pd.DataFrame, *,
    lookback: int = 20,
    min_excess_usd: float = 0.15,
    reclaim_usd: float = 0.05,
    stop_buffer_usd: float = 0.10,
    reward_risk: float = 1.5,
    max_stop_usd: float = 20.0,
) -> list[Signal]:
    """Find M1 sweeps of the preceding N continuous finished M1 candles.

    A bullish setup dips below the PRIOR N lows, then closes strictly above
    that previous low plus reclaim; bearish is symmetric. If the confirmation
    candle also sweeps the OPPOSITE edge, its intrabar order is unknowable
    from OHLC and the candle is rejected. Cross-gap lookback windows are
    rejected. Detection uses only finished candles, never later observations.
    """
    if isinstance(lookback, bool) or not isinstance(lookback, Integral) or lookback < 3:
        raise ValueError("sweep lookback must be integer >=3")
    for name, value in (
        ("min_excess_usd", min_excess_usd),
        ("reclaim_usd", reclaim_usd),
        ("stop_buffer_usd", stop_buffer_usd),
        ("reward_risk", reward_risk),
        ("max_stop_usd", max_stop_usd),
    ):
        if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    bars = aggregate_bars(minutes, "M1")
    if len(bars) <= lookback:
        return []
    for name in ("o", "h", "l", "c"):
        if (not pd.api.types.is_numeric_dtype(bars[name].dtype)
                or pd.api.types.is_bool_dtype(bars[name].dtype)):
            raise ValueError("Sweep requires numeric nonboolean OHLC")
    values = bars[["o", "h", "l", "c"]].to_numpy(dtype="float64")
    if (not np.isfinite(values).all()
            or (values <= 0).any()
            or (values[:, 1] < np.maximum(values[:, 0], values[:, 3])).any()
            or (values[:, 2] > np.minimum(values[:, 0], values[:, 3])).any()
            or (values[:, 1] < values[:, 2]).any()):
        raise ValueError("Sweep requires finite, coherent, positive M1 OHLC")
    # Vectorized M1 detection. Scanning millions of minutes with .iloc in a
    # Python loop makes grid research prohibitively slow; roll/lookback are
    # calculated in bulk and only confirmed signals become Python objects.
    prior_hi = bars["h"].rolling(lookback, min_periods=lookback).max().shift(1).to_numpy(dtype=float)
    prior_lo = bars["l"].rolling(lookback, min_periods=lookback).min().shift(1).to_numpy(dtype=float)
    highs, lows, closes = values[:, 1], values[:, 2], values[:, 3]
    continuous = np.zeros(len(bars), dtype=bool)
    continuous[lookback:] = (
        bars.index[lookback:] - bars.index[:-lookback]
        == pd.Timedelta(minutes=lookback)
    )
    crosses_high = highs > prior_hi + min_excess_usd
    crosses_low = lows < prior_lo - min_excess_usd
    single_side = crosses_high != crosses_low  # reject ambiguous dual sweeps
    buys = (crosses_low & ~crosses_high
            & (closes > prior_lo + reclaim_usd) & (closes < prior_hi))
    sells = (crosses_high & ~crosses_low
             & (closes < prior_hi - reclaim_usd) & (closes > prior_lo))
    stops = np.where(buys, closes - lows + stop_buffer_usd,
                     highs - closes + stop_buffer_usd)
    eligible = (continuous & single_side & (buys | sells)
                & np.isfinite(stops) & (stops > 0) & (stops <= max_stop_usd))
    moments = bars["close_at"].array
    signals = []
    for i in np.flatnonzero(eligible):
        side = 1 if buys[i] else -1
        stop = float(stops[i])
        signals.append(Signal(
            confirmed_at=moments[i], side=side,
            stop_distance=stop, target_distance=stop * reward_risk,
            strategy=f"sweep_reclaim_M1_{lookback}",
        ))
    return signals
