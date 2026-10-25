"""Predeclared, causal H1 regime filter for M1 BOS/Fibonacci orders.

H1 OHLC bars must be complete 60/60 observed M1 minutes. The trend for
an order uses only the latest H1 bar COMPLETED at or before the M1
signal's confirmation. No future H1 candle is used.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

from .limit_engine import LimitOrder


@dataclass(frozen=True)
class H1RegimeSettings:
    ema_span: int = 50
    slope_lag_bars: int = 5

    def __post_init__(self) -> None:
        if self.ema_span < 2 or self.slope_lag_bars < 1:
            raise ValueError("H1 EMA span >= 2 and slope lag >= 1 required")


def complete_h1_regimes(
    m1: pd.DataFrame, *, cfg: H1RegimeSettings = H1RegimeSettings()
) -> pd.DataFrame:
    """Produce strict UTC H1 candles, their close times and causal trend."""
    if not isinstance(m1.index, pd.DatetimeIndex) or m1.index.tz is None:
        raise ValueError("M1 index must be timezone aware")
    if m1.empty or m1.index.has_duplicates or not m1.index.is_monotonic_increasing:
        raise ValueError("M1 must be nonempty, sorted and unique")
    if (m1.index.asi8 % 60_000_000_000 != 0).any():
        raise ValueError("M1 timestamps must align to exact minute boundaries")
    if not {"o", "h", "l", "c"}.issubset(m1):
        raise ValueError("Missing OHLC")
    resampler = m1.resample(
        "60min", label="left", closed="left", origin="epoch"
    )
    h = resampler.agg({"o": "first", "h": "max", "l": "min", "c": "last"})
    observed = resampler["c"].count()
    h = h[observed == 60].dropna()
    h["confirmed_at"] = h.index + pd.Timedelta(hours=1)
    ema = h["c"].ewm(
        span=cfg.ema_span, min_periods=cfg.ema_span, adjust=False
    ).mean()
    previous = ema.shift(cfg.slope_lag_bars)
    h["trend"] = np.where(
        (h["c"] > ema) & (ema > previous), 1,
        np.where((h["c"] < ema) & (ema < previous), -1, 0),
    )
    return h[["confirmed_at", "trend", "c"]]


def filter_orders_h1(
    m1: pd.DataFrame,
    orders: list[LimitOrder],
    *,
    cfg: H1RegimeSettings = H1RegimeSettings(),
) -> list[LimitOrder]:
    """Retain orders aligned with previous fully closed H1 trend only."""
    if not orders:
        return []
    bars = complete_h1_regimes(m1, cfg=cfg)
    if bars.empty:
        return []
    completed_ns = bars["confirmed_at"].array.asi8
    trends = bars["trend"].to_numpy(dtype=np.int8)
    retained = []
    for order in orders:
        at = pd.Timestamp(order.placed_at)
        if at.tzinfo is None:
            raise ValueError("Order placement time must be timezone-aware")
        prior = np.searchsorted(
            completed_ns, at.tz_convert("UTC").value, side="right"
        ) - 1
        if prior >= 0 and int(trends[prior]) == order.side:
            retained.append(order)
    return retained
