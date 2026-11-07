"""Causal volatility-compression breakout on complete UTC M15/H1 candles.

Frozen exploratory hypothesis. The prior 8-bar channel is unusually narrow
versus its own prior 48-bar rolling history; the current fully closed bar
breaks out. Enters no earlier than next M1 open. Never interpolate M1 gaps.
Synthetic same-BID reference fills are NOT broker quotes/tick fills.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from .model import Signal
from .strategy import TIMEFRAMES, aggregate_bars


@dataclass(frozen=True)
class CompressionSettings:
    timeframe: str = "M15"
    range_bars: int = 8
    baseline_bars: int = 48
    contraction_ratio: float = 0.60
    breakout_buffer_usd: float = 0.25
    stop_buffer_usd: float = 0.10
    reward_risk: float = 1.8
    min_stop_usd: float = 0.75
    max_stop_usd: float = 20.0

    def __post_init__(self) -> None:
        if self.timeframe not in ("M15", "H1"):
            raise ValueError("Compression timeframe must be M15 or H1")
        if any(type(x) is not int for x in (self.range_bars, self.baseline_bars)):
            raise ValueError("Compression bar counts must be integers, never bool")
        if not (self.range_bars >= 3 and self.baseline_bars >= 3 * self.range_bars):
            raise ValueError("Compression baseline must cover at least three ranges")
        for x in (self.contraction_ratio, self.breakout_buffer_usd, self.stop_buffer_usd,
                  self.reward_risk, self.min_stop_usd, self.max_stop_usd):
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0:
                raise ValueError("Compression parameters require finite positive numbers")
        if self.contraction_ratio >= 1 or self.min_stop_usd > self.max_stop_usd:
            raise ValueError("Compression ratio must be below 1 and stop bounds ordered")


def compression_breakout_signals(
    minutes: pd.DataFrame, *, settings: CompressionSettings = CompressionSettings(),
) -> list[Signal]:
    bars = aggregate_bars(minutes, settings.timeframe)
    n, history = settings.range_bars, settings.baseline_bars
    if len(bars) < n + history:
        return []
    # The current candle is never used in a baseline, range or threshold.
    prior_high = bars["h"].shift(1).rolling(n, min_periods=n).max()
    prior_low = bars["l"].shift(1).rolling(n, min_periods=n).min()
    width = prior_high - prior_low
    historical_width = width.shift(1).rolling(
        history, min_periods=history
    ).median()
    step = pd.Timedelta(minutes=TIMEFRAMES[settings.timeframe])
    signals: list[Signal] = []
    # Discard windows bridging any quote closure; no artificial contraction.
    consecutive = bars.index.to_series().diff().eq(step)
    complete_window = consecutive.rolling(n + 1, min_periods=n + 1).sum().eq(n + 1)
    for i in range(n + history, len(bars)):
        if not bool(complete_window.iloc[i]):
            continue
        hi, lo = float(prior_high.iloc[i]), float(prior_low.iloc[i])
        median = float(historical_width.iloc[i])
        if not (math.isfinite(median) and median > 0 and 0 < hi - lo <= median * settings.contraction_ratio):
            continue
        current = bars.iloc[i]
        # Only a candle OPENING INSIDE the prior range may signal: exclude
        # pure quote-reopen jumps and non-causal gap breakout recognition.
        if not lo <= current["o"] <= hi:
            continue
        up = current["c"] >= hi + settings.breakout_buffer_usd
        down = current["c"] <= lo - settings.breakout_buffer_usd
        if up == down:
            continue
        side = 1 if up else -1
        distance = (float(current["c"] - lo) if up
                    else float(hi - current["c"])) + settings.stop_buffer_usd
        if not settings.min_stop_usd <= distance <= settings.max_stop_usd:
            continue
        signals.append(Signal(
            confirmed_at=current["close_at"],
            side=side,
            stop_distance=distance,
            target_distance=distance * settings.reward_risk,
            strategy=f"compression_breakout_{settings.timeframe}_{n}_{history}",
        ))
    return signals
