"""Frozen ORB-01: fixed-UTC M15 morning opening-range continuation.

This is a research hypothesis, not a validated trading system. Complete
M15 candles only; the opening range and breakout close are observed before
any next-M1 entry can occur. UTC is deliberately fixed, NOT claimed to
follow London/NY daylight saving time.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from .model import Signal
from .strategy import aggregate_bars


@dataclass(frozen=True)
class OpeningRangeSettings:
    start_hour_utc: int = 6
    opening_minutes: int = 60
    trade_window_minutes: int = 240
    breakout_buffer_usd: float = 0.20
    stop_buffer_usd: float = 0.10
    min_range_usd: float = 0.75
    max_range_usd: float = 8.0
    min_stop_usd: float = 0.75
    max_stop_usd: float = 20.0
    reward_risk: float = 1.5

    def __post_init__(self) -> None:
        if type(self.start_hour_utc) is not int or not 0 <= self.start_hour_utc < 24:
            raise ValueError("UTC start hour must be integer 0-23")
        if type(self.opening_minutes) is not int or self.opening_minutes != 60:
            raise ValueError("Frozen opening range must be 60 minutes")
        if type(self.trade_window_minutes) is not int or self.trade_window_minutes != 240:
            raise ValueError("Frozen trading window must be 240 minutes")
        if self.start_hour_utc + (self.opening_minutes + self.trade_window_minutes) / 60 > 24:
            raise ValueError("Window must remain within a UTC calendar day")
        for name in ("breakout_buffer_usd", "stop_buffer_usd", "min_range_usd",
                     "max_range_usd", "min_stop_usd", "max_stop_usd", "reward_risk"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite positive")
        if self.min_range_usd > self.max_range_usd or self.min_stop_usd > self.max_stop_usd:
            raise ValueError("Minimum/maximum range or stop inverted")


def opening_range_signals(
    minutes: pd.DataFrame, *, settings: OpeningRangeSettings = OpeningRangeSettings(),
) -> list[Signal]:
    bars = aggregate_bars(minutes, "M15")
    if bars.empty:
        return []
    signals: list[Signal] = []
    width = pd.Timedelta(minutes=15)
    for day, group in bars.groupby(bars.index.normalize(), sort=True):
        begin = day + pd.Timedelta(hours=settings.start_hour_utc)
        opening_end = begin + pd.Timedelta(minutes=settings.opening_minutes)
        trade_end = opening_end + pd.Timedelta(minutes=settings.trade_window_minutes)
        opening_idx = pd.date_range(begin, periods=4, freq="15min")
        if not opening_idx.isin(group.index).all():
            continue
        opening = group.loc[opening_idx]
        hi = float(opening["h"].max())
        lo = float(opening["l"].min())
        if not settings.min_range_usd <= hi - lo <= settings.max_range_usd:
            continue
        expected_next = opening_end
        prev_close = float(opening.iloc[-1]["c"])
        for timestamp, bar in group.loc[(group.index >= opening_end) & (group.index < trade_end)].iterrows():
            # A missing M15 candle invalidates the rest of the session: no
            # re-open breakout falsely classified as a continuous move.
            if timestamp != expected_next:
                break
            expected_next += width
            op, close = float(bar["o"]), float(bar["c"])
            # Crossing must start within range and previous candle must end
            # within range. Reject gaps and repeated outside closes.
            if lo <= op <= hi and lo <= prev_close <= hi:
                up = close >= hi + settings.breakout_buffer_usd
                down = close <= lo - settings.breakout_buffer_usd
                if up != down:
                    side = 1 if up else -1
                    distance = (close - lo if up else hi - close) + settings.stop_buffer_usd
                    if settings.min_stop_usd <= distance <= settings.max_stop_usd:
                        signals.append(Signal(
                            confirmed_at=bar["close_at"], side=side,
                            stop_distance=distance,
                            target_distance=distance * settings.reward_risk,
                            strategy="opening_range_fixed_utc_0600_M15_1h_4h",
                        ))
                    # Only the first valid close crossing may be evaluated
                    # per session, even if risk bound rejects its stop.
                    break
            prev_close = close
    return signals
