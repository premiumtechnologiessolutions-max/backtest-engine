"""Three-candle Fair Value Gap research rules (not complete proprietary ICT).

Generates limit orders only after the third FULL H1 bar closes. No future
price is used to place an order. The M1 limit replay owns fill/stop rules.
"""
from __future__ import annotations

import pandas as pd

from .limit_engine import LimitOrder
from .strategy import aggregate_bars


def fvg_midpoint_limit_orders(
    minutes: pd.DataFrame,
    *,
    timeframe: str = "H1",
    min_gap_usd: float = 0.5,
    stop_buffer_usd: float = 0.1,
    reward_to_risk: float = 2.0,
    expiry_hours: float = 20.0,
) -> list[LimitOrder]:
    """Create 3-bar FVG midpoint (CE) limit-entry setups.

    Bullish: low of third completed bar > high of first completed bar.
    Bearish: high of third completed bar < low of first completed bar.
    A setup's limit price is the gap midpoint. Stop is beyond candle 1
    extreme, with buffer, target is fixed R multiple. Orders expire
    after a fixed elapsed UTC interval (not trading hours).

    Deliberately NO extra displacement-strength, BOS/CHoCH, session,
    or proprietary ICT confirmation unless added as explicit new rules.
    """
    if any(not (v > 0) for v in (
        min_gap_usd, stop_buffer_usd, reward_to_risk, expiry_hours
    )):
        raise ValueError("All FVG parameters must be positive")
    bars = aggregate_bars(minutes, timeframe)
    if len(bars) < 3:
        return []
    orders: list[LimitOrder] = []
    for i in range(2, len(bars)):
        first = bars.iloc[i - 2]
        third = bars.iloc[i]
        confirmed = pd.Timestamp(third["close_at"])
        gap_up = float(third["l"] - first["h"])
        gap_down = float(first["l"] - third["h"])
        if gap_up >= min_gap_usd:
            midpoint = (float(third["l"]) + float(first["h"])) / 2
            stop = float(first["l"]) - stop_buffer_usd
            distance = midpoint - stop
            if distance <= 0:
                continue
            orders.append(LimitOrder(
                placed_at=confirmed,
                expires_at=confirmed + pd.Timedelta(hours=expiry_hours),
                side=1, price=midpoint, stop=stop,
                target=midpoint + reward_to_risk * distance,
                strategy=f"fvg3_ce_{timeframe}_bullish",
            ))
        elif gap_down >= min_gap_usd:
            midpoint = (float(first["l"]) + float(third["h"])) / 2
            stop = float(first["h"]) + stop_buffer_usd
            distance = stop - midpoint
            if distance <= 0:
                continue
            orders.append(LimitOrder(
                placed_at=confirmed,
                expires_at=confirmed + pd.Timedelta(hours=expiry_hours),
                side=-1, price=midpoint, stop=stop,
                target=midpoint - reward_to_risk * distance,
                strategy=f"fvg3_ce_{timeframe}_bearish",
            ))
    return orders
