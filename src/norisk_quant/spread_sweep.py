"""FAC024: causal M15 liquidity sweep plus M1 BID/ASK spread recovery.

Frozen prospective hypothesis; not validated on original gold or live ticks.
Signals use only completed bars, and require a contiguous 60-minute spread
baseline preceding the 15-minute sweep. No forward data is inspected.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

import numpy as np
import pandas as pd

from .liquidity_sweep import SweepSettings, liquidity_sweep_signals
from .model import Signal


@dataclass(frozen=True)
class SpreadSweepSettings:
    lookback_m15: int = 12
    penetration_usd: float = 0.25
    spread_baseline_minutes: int = 60
    initial_spread_multiple: float = 1.5
    recovered_spread_multiple: float = 1.1
    stop_buffer_usd: float = 0.10
    reward_risk: float = 1.5

    def __post_init__(self) -> None:
        if (type(self.lookback_m15) is not int or self.lookback_m15 != 12
                or type(self.spread_baseline_minutes) is not int
                or self.spread_baseline_minutes != 60):
            raise ValueError("FAC024 lookback and baseline are frozen at 12 M15 / 60 M1")
        frozen = (('penetration_usd', self.penetration_usd, 0.25),
                  ('initial_spread_multiple', self.initial_spread_multiple, 1.5),
                  ('recovered_spread_multiple', self.recovered_spread_multiple, 1.1),
                  ('stop_buffer_usd', self.stop_buffer_usd, 0.10),
                  ('reward_risk', self.reward_risk, 1.5))
        for name, value, expected in frozen:
            if (isinstance(value, bool) or not isinstance(value, Real)
                    or not np.isfinite(value) or value != expected):
                raise ValueError(f"FAC024 {name} is frozen at {expected}")


def spread_recovery_sweep_signals(
    minutes: pd.DataFrame,
    *,
    settings: SpreadSweepSettings = SpreadSweepSettings(),
) -> list[Signal]:
    """Return next-M1-open-eligible signals only after the M15 sweep closes.

    Spread expansion is measured at the sweep's first M1 OPEN; recovery at
    its last M1 CLOSE. Baseline uses the 60 earlier M1 CLOSE spreads only.
    This is M1 candle spread, NOT tick-order or broker-fill verification.
    """
    if not isinstance(minutes.index, pd.DatetimeIndex) or minutes.empty:
        raise ValueError("FAC024 requires nonempty UTC M1 DatetimeIndex")
    index = minutes.index
    if (index.tz is None or str(index.tz) != "UTC" or index.hasnans
            or index.has_duplicates or not index.is_monotonic_increasing):
        raise ValueError("FAC024 requires unique sorted UTC M1 opens")
    stamps = index.as_unit("ns").asi8
    if (stamps % 60_000_000_000 != 0).any():
        raise ValueError("FAC024 M1 opens must be minute-aligned")
    required = ('o', 'h', 'l', 'c', 'ao', 'ah', 'al', 'ac')
    if not minutes.columns.is_unique:
        raise ValueError("FAC024 requires unique quote column names")
    if any(k not in minutes for k in required):
        raise ValueError("FAC024 requires original M1 BID/ASK OHLC")
    for col in required:
        dtype = minutes[col].dtype
        if (not pd.api.types.is_numeric_dtype(dtype)
                or pd.api.types.is_bool_dtype(dtype)
                or pd.api.types.is_complex_dtype(dtype)):
            raise ValueError("FAC024 BID/ASK must be real numeric non-boolean")
    values = minutes[list(required)].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("FAC024 requires finite positive BID/ASK OHLC")
    if (values[:, 4:] < values[:, :4]).any():
        raise ValueError("FAC024 rejects crossed BID/ASK quotes")
    # A malformed minute candle can fabricate a sweep even when BID <= ASK.
    # Validate both envelopes before aggregation; do not alter frozen signals.
    for offset in (0, 4):
        op, hi, lo, cl = (values[:, offset + j] for j in range(4))
        if ((hi < np.maximum(op, cl)).any()
                or (lo > np.minimum(op, cl)).any()
                or (hi < lo).any()):
            raise ValueError("FAC024 invalid BID/ASK OHLC bar geometry")

    prior = settings.spread_baseline_minutes
    spread_close = (minutes['ac'] - minutes['c']).to_numpy(dtype=float)
    spread_open = (minutes['ao'] - minutes['o']).to_numpy(dtype=float)
    sweep = SweepSettings(
        timeframe='M15', lookback_bars=settings.lookback_m15,
        penetration_usd=settings.penetration_usd,
        stop_buffer_usd=settings.stop_buffer_usd,
        reward_risk=settings.reward_risk,
    )
    base_signals = liquidity_sweep_signals(minutes, settings=sweep)
    accepted: list[Signal] = []
    for signal in base_signals:
        end_ns = pd.Timestamp(signal.confirmed_at).tz_convert('UTC').value
        begin_ns = end_ns - 15 * 60_000_000_000
        pos = int(np.searchsorted(stamps, begin_ns))
        if pos < prior or pos + 15 > len(stamps):
            continue
        window = stamps[pos - prior:pos + 15]
        if (window[0] != begin_ns - prior * 60_000_000_000
                or window[-1] != end_ns - 60_000_000_000
                or not np.all(np.diff(window) == 60_000_000_000)):
            continue
        earlier = spread_close[pos - prior:pos]
        baseline = float(np.median(earlier))
        if not np.isfinite(baseline) or baseline <= 0:
            continue
        if (spread_open[pos] >= settings.initial_spread_multiple * baseline
                and spread_close[pos + 14] <= settings.recovered_spread_multiple * baseline):
            accepted.append(Signal(
                confirmed_at=signal.confirmed_at,
                side=signal.side,
                stop_distance=signal.stop_distance,
                target_distance=signal.target_distance,
                strategy='FAC024_M15_SPREAD_RECOVERY_SWEEP_FROZEN',
            ))
    return accepted
