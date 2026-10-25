"""Causal M1 swing-structure BOS + Fibonacci Golden Zone limit research.

Not a complete manual SMC/ICT interpretation: all discretionary choices are
made reproducible here. No future candle contributes to any live signal.

Wave 1/2 here means the first two *distinct BOS events* in each detected
same-side structure regime. This is an explicit mechanical proxy, not an
Elliott-wave classifier or an assertion about the chart's handwritten count.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .limit_engine import LimitOrder


@dataclass(frozen=True)
class BosFibSettings:
    pivot_left: int = 3
    pivot_right: int = 3
    fib_entry: float = 0.618
    zone_lower: float = 0.618
    zone_upper: float = 0.786
    reward_risk: float = 1.0
    sl_buffer_usd: float = 0.10
    min_break_usd: float = 0.10
    min_impulse_usd: float = 1.0
    expiry_minutes: int = 120
    max_bos_waves_per_regime: int = 2

    def __post_init__(self) -> None:
        if self.pivot_left < 1 or self.pivot_right < 1:
            raise ValueError("Pivot confirmation must be >=1 on both sides")
        if not (0 < self.zone_lower <= self.fib_entry <= self.zone_upper < 1):
            raise ValueError("Fib entry must lie within 0<Golden Zone<1")
        if not (self.reward_risk > 0 and math.isfinite(self.reward_risk)):
            raise ValueError("reward_risk must be finite positive")
        if any(not (math.isfinite(x) and x > 0) for x in (
            self.sl_buffer_usd, self.min_break_usd, self.min_impulse_usd
        )):
            raise ValueError("Buffers/minimum impulse must be finite positive")
        if self.expiry_minutes < 1 or self.max_bos_waves_per_regime < 1:
            raise ValueError("Expiry and max waves must be positive")


def bos_fib_limit_orders(
    minutes: pd.DataFrame, *, settings: BosFibSettings = BosFibSettings(),
) -> list[LimitOrder]:
    """Construct closed-candle BOS pullback orders, with confirmed pivots.

    Uptrend: last TWO confirmed pivot highs AND lows are rising; a closed
    M1 candle crosses above the most recently confirmed high by min_break;
    most recent confirmed low is *after* that high. Mirror for downtrend.

    Confirming a pivot at index j requires pivot_right FUTURE candles,
    so pivot j becomes usable only at index j+pivot_right. Entry orders
    become active on the first observed M1 open after BOS candle CLOSE.
    BUY Fibonacci impulse starts at confirmed low and ends at the highest
    high observed until BOS; SELL impulse starts at confirmed high and ends
    at lowest low. Fixed 0.618 entry defaults to the FIRST edge of zone
    0.618–0.786. SL is past anchor; TP = 1R (configurable).

    Any gap inside the local pivot window invalidates that pivot;
    if a gap occurs anywhere from the anchor swing through BOS,
    no order is created. This avoids inventing continuous price structure
    through weekend closures or data outages.
    """
    if not isinstance(minutes.index, pd.DatetimeIndex) or minutes.index.tz is None:
        raise ValueError("Expected timezone-aware, ordered M1 candles")
    if minutes.index.has_duplicates or not minutes.index.is_monotonic_increasing:
        raise ValueError("M1 timestamps must be unique and increasing")
    if not {"o", "h", "l", "c"}.issubset(minutes.columns):
        raise ValueError("Missing OHLC candles")
    if minutes.empty:
        return []
    ix = minutes.index
    stamp = ix.asi8
    step = 60_000_000_000
    if (stamp % step != 0).any() or not (stamp[1:] > stamp[:-1]).all():
        raise ValueError("M1 timestamps must align to minute boundaries")
    vals = minutes[["o", "h", "l", "c"]].to_numpy(dtype=np.float64)
    if not np.isfinite(vals).all():
        raise ValueError("Invalid OHLC NaN/infinity")
    opening, high, low, close = vals.T
    if ((low <= 0) | (low > np.minimum(opening, close)) |
        (high < np.maximum(opening, close))).any():
        raise ValueError("Invalid OHLC bar range")

    discontinuity = np.r_[False, (stamp[1:] - stamp[:-1]) != step]
    # Number of gaps up to and including i, for O(1) continuity checks.
    gap_count = np.cumsum(discontinuity.astype(np.int64))
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    used_high = -1
    used_low = -1
    regime_side = 0
    regime_waves = 0
    orders: list[LimitOrder] = []
    left, right = settings.pivot_left, settings.pivot_right

    for i in range(left + right, len(ix)):
        j = i - right
        if gap_count[i] == gap_count[j - left]:
            # Pivot tie convention: strict vs left, inclusive vs right;
            # makes duplicate highs deterministic and does not revise pivots.
            if high[j] > max(high[j-left:j]) and high[j] >= max(high[j+1:i+1]):
                highs.append((j, float(high[j])))
                if len(highs) > 3:
                    highs.pop(0)
            if low[j] < min(low[j-left:j]) and low[j] <= min(low[j+1:i+1]):
                lows.append((j, float(low[j])))
                if len(lows) > 3:
                    lows.pop(0)
        if len(highs) < 2 or len(lows) < 2 or i == 0:
            continue
        trend = (1 if highs[-1][1] > highs[-2][1] and lows[-1][1] > lows[-2][1]
                 else -1 if highs[-1][1] < highs[-2][1] and lows[-1][1] < lows[-2][1]
                 else 0)
        side = 0
        anchor_idx = -1
        if trend == 1:
            hidx, hprice = highs[-1]
            anchor_idx, anchor = lows[-1]
            threshold = hprice + settings.min_break_usd
            if (hidx > used_high and anchor_idx > hidx and
                    close[i] > threshold and close[i-1] <= threshold):
                side = 1
                used_high = hidx
        elif trend == -1:
            lidx, lprice = lows[-1]
            anchor_idx, anchor = highs[-1]
            threshold = lprice - settings.min_break_usd
            if (lidx > used_low and anchor_idx > lidx and
                    close[i] < threshold and close[i-1] >= threshold):
                side = -1
                used_low = lidx
        if not side:
            continue
        if side != regime_side:
            regime_side, regime_waves = side, 0
        regime_waves += 1
        if regime_waves > settings.max_bos_waves_per_regime:
            continue
        # Recheck that the entire impulse is OBSERVED minute-by-minute.
        if gap_count[i] != gap_count[anchor_idx]:
            continue
        if side == 1:
            extreme = float(np.max(high[anchor_idx:i+1]))
            distance = extreme - anchor
            entry = extreme - settings.fib_entry * distance
            stop = anchor - settings.sl_buffer_usd
            risk = entry - stop
            target = entry + settings.reward_risk * risk
        else:
            extreme = float(np.min(low[anchor_idx:i+1]))
            distance = anchor - extreme
            entry = extreme + settings.fib_entry * distance
            stop = anchor + settings.sl_buffer_usd
            risk = stop - entry
            target = entry - settings.reward_risk * risk
        if not (distance >= settings.min_impulse_usd and risk > 0 and target > 0):
            continue
        confirmed_at = ix[i] + pd.Timedelta(minutes=1)
        orders.append(LimitOrder(
            placed_at=confirmed_at,
            expires_at=confirmed_at + pd.Timedelta(minutes=settings.expiry_minutes),
            side=side, price=entry, stop=stop, target=target,
            strategy=f"bos_fib_m1_wave{regime_waves}_r{settings.reward_risk:g}_fib{settings.fib_entry:g}",
        ))
    return orders
