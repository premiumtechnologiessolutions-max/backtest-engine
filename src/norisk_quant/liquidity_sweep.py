"""Causal, close-confirmed liquidity sweep/reclaim research hypothesis.

Previous channel uses only COMPLETE prior UTC higher-timeframe bars;
current sweep qualifies at close, next M1 open is the earliest entry.
Unvalidated research, no real broker-tick fill claims.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import pandas as pd
from .model import Signal
from .strategy import TIMEFRAMES, aggregate_bars


@dataclass(frozen=True)
class SweepSettings:
    timeframe: str = "M15"
    lookback_bars: int = 12
    penetration_usd: float = 0.25
    stop_buffer_usd: float = 0.10
    reward_risk: float = 1.5
    min_stop_usd: float = 0.50
    max_stop_usd: float = 50.0

    def __post_init__(self) -> None:
        if self.timeframe not in ("M15", "H1"):
            raise ValueError("Sweep timeframe must be M15 or H1")
        if type(self.lookback_bars) is not int or self.lookback_bars < 3:
            raise ValueError("Sweep lookback must be integer >= 3")
        for value in (self.penetration_usd, self.stop_buffer_usd,
                      self.reward_risk, self.min_stop_usd, self.max_stop_usd):
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value <= 0):
                raise ValueError("Sweep parameters must be finite positive")
        if self.min_stop_usd > self.max_stop_usd:
            raise ValueError("Invalid stop range")


def liquidity_sweep_signals(
    minutes: pd.DataFrame, *, settings: SweepSettings = SweepSettings(),
) -> list[Signal]:
    bars = aggregate_bars(minutes, settings.timeframe)
    if len(bars) < settings.lookback_bars + 1:
        return []
    prior_high = bars["h"].shift(1).rolling(
        settings.lookback_bars, min_periods=settings.lookback_bars
    ).max()
    prior_low = bars["l"].shift(1).rolling(
        settings.lookback_bars, min_periods=settings.lookback_bars
    ).min()
    period = pd.Timedelta(minutes=TIMEFRAMES[settings.timeframe])
    signals = []
    for i in range(settings.lookback_bars, len(bars)):
        candle = bars.iloc[i]
        top, bottom = float(prior_high.iloc[i]), float(prior_low.iloc[i])
        if (not math.isfinite(top) or not math.isfinite(bottom)
                or bars.index[i] - bars.index[i - 1] != period):
            continue
        low_sweep = (
            candle["l"] <= bottom - settings.penetration_usd
            and bottom < candle["c"] <= top
        )
        high_sweep = (
            candle["h"] >= top + settings.penetration_usd
            and bottom <= candle["c"] < top
        )
        if low_sweep == high_sweep:
            continue  # no sweep or ambiguous two-sided sweep
        side = 1 if low_sweep else -1
        stop = (float(candle["c"] - candle["l"]) if low_sweep
                else float(candle["h"] - candle["c"])) + settings.stop_buffer_usd
        if not settings.min_stop_usd <= stop <= settings.max_stop_usd:
            continue
        signals.append(Signal(
            confirmed_at=candle["close_at"], side=side,
            stop_distance=stop, target_distance=stop * settings.reward_risk,
            strategy=f"sweep_reclaim_{settings.timeframe}_{settings.lookback_bars}",
        ))
    return signals
