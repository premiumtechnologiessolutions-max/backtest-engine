"""Predeclared New York 08:20–09:00 range: breakout vs rejection.

Timezone conversion uses IANA America/New_York, not hardcoded UTC offset.
Requires all 40 contiguous M1 quotes in the morning range and a complete
post-09:00 M5 trigger candle. No tick-path inference, no live fills.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
import math

import pandas as pd

from .model import Signal
from .strategy import aggregate_bars

NY = "America/New_York"


@dataclass(frozen=True)
class NewYorkOpenSettings:
    variant: str = "breakout"
    penetration_usd: float = 0.25
    stop_buffer_usd: float = 0.10
    min_stop_usd: float = 0.75
    max_stop_usd: float = 20.0
    reward_risk: float = 1.8

    def __post_init__(self) -> None:
        if self.variant not in ("breakout", "rejection"):
            raise ValueError("NY morning variant must be breakout or rejection")
        for value in (self.penetration_usd, self.stop_buffer_usd,
                      self.min_stop_usd, self.max_stop_usd, self.reward_risk):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("NY morning parameters must be finite and positive")
        if self.min_stop_usd > self.max_stop_usd:
            raise ValueError("NY stop range is inverted")


def ny_open_signals(minutes: pd.DataFrame, *, settings: NewYorkOpenSettings = NewYorkOpenSettings()) -> list[Signal]:
    if minutes.empty:
        return []
    if not isinstance(minutes.index, pd.DatetimeIndex) or minutes.index.tz is None or str(minutes.index.tz) != "UTC":
        raise ValueError("M1 must have explicit UTC index")
    if minutes.index.hasnans or minutes.index.has_duplicates or not minutes.index.is_monotonic_increasing:
        raise ValueError("M1 must be unique and sorted")
    if (minutes.index.as_unit("ns").asi8 % 60_000_000_000 != 0).any():
        raise ValueError("M1 timestamps must be minute opens")

    local = minutes.index.tz_convert(NY)
    morning = (local.hour == 8) & (local.minute >= 20)
    observed = minutes.loc[morning]
    if observed.empty:
        return []
    local_morning = observed.index.tz_convert(NY)
    dates = pd.Series(local_morning.date, index=observed.index)
    daily_range: dict[object, tuple[float, float]] = {}
    for day, part in observed.groupby(dates):
        # Exactly 08:20, 08:21, ..., 08:59 in New York local time.
        if len(part) != 40 or not (part.index.to_series().diff().iloc[1:] == pd.Timedelta(minutes=1)).all():
            continue
        if (part.index.tz_convert(NY)[0].time() != time(8, 20)
                or part.index.tz_convert(NY)[-1].time() != time(8, 59)):
            continue
        daily_range[day] = (float(part["h"].max()), float(part["l"].min()))

    full_m5 = aggregate_bars(minutes, "M5")
    results = []
    processed: set[object] = set()
    for _, candle in full_m5.iterrows():
        signal_at = pd.Timestamp(candle["close_at"])
        ny_at = signal_at.tz_convert(NY)
        if not (time(9, 5) <= ny_at.time() <= time(11, 0)):
            continue
        day = ny_at.date()
        if day in processed or day not in daily_range:
            continue
        high, low = daily_range[day]
        if not (math.isfinite(high) and math.isfinite(low) and high > low
                and low <= candle["o"] <= high):
            continue
        penetration = settings.penetration_usd
        if settings.variant == "breakout":
            up = candle["c"] >= high + penetration
            down = candle["c"] <= low - penetration
            if up == down:
                continue
            side = 1 if up else -1
            stop_distance = (float(candle["c"] - low) if up
                             else float(high - candle["c"])) + settings.stop_buffer_usd
        else:
            # Reversal ONLY after the observed M5 wick breaches the range and
            # the same M5 candle closes back inside; if both sides breached,
            # no directional information is defensible without intrabar ticks.
            up_sweep = candle["h"] >= high + penetration and low < candle["c"] < high
            down_sweep = candle["l"] <= low - penetration and low < candle["c"] < high
            if up_sweep == down_sweep:
                continue
            side = -1 if up_sweep else 1
            stop_distance = (float(candle["h"] - candle["c"]) if up_sweep
                             else float(candle["c"] - candle["l"])) + settings.stop_buffer_usd
        if not settings.min_stop_usd <= stop_distance <= settings.max_stop_usd:
            continue
        processed.add(day)
        results.append(Signal(
            confirmed_at=signal_at, side=side,
            stop_distance=stop_distance,
            target_distance=stop_distance * settings.reward_risk,
            strategy=f"ny_morning_{settings.variant}_0820_0900",
        ))
    return results
