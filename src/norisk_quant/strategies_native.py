"""Reproducible entry strategy variants; not validated trading advice."""
from __future__ import annotations

import pandas as pd

from .model import Signal
from .strategy import aggregate_bars


def donchian_breakout_signals(
    minutes: pd.DataFrame, *,
    timeframe: str = "H1",
    lookback: int = 20,
    stop_distance: float = 15.0,
    target_distance: float = 30.0,
) -> list[Signal]:
    """Close-confirmed Donchian price-channel breakout.

    Signals at end of a FULL timeframe candle only. Prior channel values
    are shifted one bar to prohibit the breakout candle looking at itself.

    SL/TP here use user-supplied USD-per-ounce DISTANCES (15/30 defaults),
    NOT the classic Turtle system's scale-in / 10-bar exit protocol.
    This is explicitly a different and simplified research variant.
    """
    if lookback < 2 or stop_distance <= 0 or target_distance <= 0:
        raise ValueError("Invalid Donchian parameters")
    bars = aggregate_bars(minutes, timeframe)
    if len(bars) < lookback + 1:
        return []
    hi = bars["h"].rolling(lookback, min_periods=lookback).max().shift(1)
    lo = bars["l"].rolling(lookback, min_periods=lookback).min().shift(1)
    signals = []
    for i in range(lookback, len(bars)):
        side = 1 if bars["c"].iloc[i] > hi.iloc[i] else (
            -1 if bars["c"].iloc[i] < lo.iloc[i] else 0
        )
        if side:
            signals.append(
                Signal(
                    confirmed_at=bars["close_at"].iloc[i],
                    side=side,
                    stop_distance=stop_distance,
                    target_distance=target_distance,
                    strategy=f"donchian_close_{timeframe}_{lookback}_fixedSLTP",
                )
            )
    return signals
