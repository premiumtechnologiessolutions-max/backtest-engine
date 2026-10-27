from __future__ import annotations

import pandas as pd

from .model import Signal

TIMEFRAMES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240}


def aggregate_bars(minutes: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Make ONLY complete UTC-anchored M1-based candles.

    A 170-of-240 observed-minutes H4 candle is NOT complete; it must not
    influence signals or indicators. Partial daily/weekend candles are
    discarded rather than interpolated. Broker-server timezone-specific
    H4/D1 candles need separate explicit source metadata and anchoring.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    required = {"o", "h", "l", "c"}
    if not required.issubset(minutes.columns):
        raise ValueError("M1 OHLC columns required")
    if not isinstance(minutes.index, pd.DatetimeIndex) or minutes.index.tz is None:
        raise ValueError("Source candles must have timezone-aware UTC DatetimeIndex")
    if minutes.index.has_duplicates or not minutes.index.is_monotonic_increasing:
        raise ValueError("Source M1 dates must be sorted and unique")
    # DatetimeIndex.asi8 uses the index's own unit (s/ms/us/ns), not
    # necessarily nanoseconds. A fixed nanosecond modulo incorrectly rejects
    # valid M1 bars when Pandas preserves second/millisecond precision.
    # Normalize before floor(): a local timezone may contain ambiguous DST
    # wall-clock minutes even though its UTC instants are unambiguous.
    utc_index = minutes.index.tz_convert("UTC")
    if (utc_index != utc_index.floor("min")).any():
        raise ValueError("M1 candle opens must align exactly to minute boundaries")
    if minutes[list(required)].isna().any().any():
        raise ValueError("NaN in M1 source; never construct a fabricated full candle")
    width = TIMEFRAMES[timeframe]
    if width == 1:
        out = minutes[["o", "h", "l", "c"]].copy()
        out["close_at"] = out.index + pd.Timedelta(minutes=1)
        return out
    rule = f"{width}min"
    resampler = minutes.resample(rule, label="left", closed="left", origin="epoch")
    bars = resampler.agg({"o": "first", "h": "max", "l": "min", "c": "last"})
    counts = resampler["c"].count()
    # Drop incomplete candles rather than unknowingly inventing prices.
    bars = bars[counts == width].dropna()
    bars["close_at"] = bars.index + pd.Timedelta(minutes=width)
    return bars


def ema_cross_signals(
    minutes: pd.DataFrame,
    *,
    timeframe: str = "M15",
    fast: int = 9,
    slow: int = 21,
    atr_period: int = 14,
    stop_atr: float = 1.5,
    rr: float = 2.0,
) -> list[Signal]:
    """Proof-of-architecture plug-in, not a validated gold strategy."""
    if not (fast > 0 and slow > fast and atr_period > 0 and stop_atr > 0 and rr > 0):
        raise ValueError("Invalid EMA/ATR parameters")
    bars = aggregate_bars(minutes, timeframe)
    if len(bars) < max(slow, atr_period) + 2:
        return []
    ef = bars["c"].ewm(span=fast, adjust=False).mean()
    es = bars["c"].ewm(span=slow, adjust=False).mean()
    tr = pd.concat(
        [
            bars["h"] - bars["l"],
            (bars["h"] - bars["c"].shift(1)).abs(),
            (bars["l"] - bars["c"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / atr_period, adjust=False).mean()
    bullish = (ef > es) & (ef.shift(1) <= es.shift(1))
    bearish = (ef < es) & (ef.shift(1) >= es.shift(1))
    signals = []
    for idx in range(max(slow, atr_period) + 1, len(bars)):
        if not (bool(bullish.iloc[idx]) or bool(bearish.iloc[idx])):
            continue
        stop = float(atr.iloc[idx] * stop_atr)
        if pd.isna(stop) or stop <= 0:
            continue
        signals.append(
            Signal(
                confirmed_at=bars["close_at"].iloc[idx],
                side=1 if bool(bullish.iloc[idx]) else -1,
                stop_distance=stop,
                target_distance=stop * rr,
                strategy=f"ema_cross_{timeframe}_{fast}_{slow}",
            )
        )
    return signals
