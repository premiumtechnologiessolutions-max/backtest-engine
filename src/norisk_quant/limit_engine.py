"""Conservative M1 OHLC limit-entry simulator for FVG/OB research.

This is NOT real tick path or broker execution. It deliberately assumes
entry and stop can both occur during the same M1 candle, and stops first
if the candle range is ambiguous. Pending orders use absolute prices.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .execution import Result
from .model import Position, Settings


@dataclass(frozen=True)
class LimitOrder:
    placed_at: pd.Timestamp
    expires_at: pd.Timestamp
    side: int
    price: float
    stop: float
    target: float
    strategy: str = "limit_unspecified"

    def __post_init__(self) -> None:
        placed, expires = pd.Timestamp(self.placed_at), pd.Timestamp(self.expires_at)
        if placed.tzinfo is None or expires.tzinfo is None:
            raise ValueError("Limit order timestamps must specify UTC offset")
        if expires < placed:
            raise ValueError("Limit expires before being placed")
        if self.side not in (1, -1):
            raise ValueError("Limit side must be +1 or -1")
        for n in (self.price, self.stop, self.target):
            if not np.isfinite(n) or n <= 0:
                raise ValueError("Limit prices must be finite positive numbers")
        if self.side == 1 and not self.stop < self.price < self.target:
            raise ValueError("Buy limit requires stop < limit < target")
        if self.side == -1 and not self.target < self.price < self.stop:
            raise ValueError("Sell limit requires target < limit < stop")


def run_limits(minutes: pd.DataFrame, orders: list[LimitOrder], settings: Settings) -> Result:
    """One-position M1 replay with oldest eligible pending limit order priority.

    A pending limit can be filled only on an observed M1 candle whose start
    is on/after placement, and not after expiration. When touched inside M1,
    fill conservatively AT LIMIT (no gap improvement). If the reopening
    market price is already beyond the configured stop, stop at that adverse
    first-observed OPEN. Stop-first is assumed if intrabar order ambiguous.
    """
    if minutes.empty or not isinstance(minutes.index, pd.DatetimeIndex):
        raise ValueError("Nonempty M1 DatetimeIndex required")
    if minutes.index.tz is None or minutes.index.has_duplicates or not minutes.index.is_monotonic_increasing:
        raise ValueError("Sorted timezone-aware M1 index required")
    if not {"o", "h", "l", "c"}.issubset(minutes):
        raise ValueError("Missing M1 reference OHLC")
    for order in orders:
        if not isinstance(order, LimitOrder):
            raise TypeError("Expected LimitOrder objects")
    queued = sorted(orders, key=lambda a: pd.Timestamp(a.placed_at))
    cursor = 0
    pending: list[LimitOrder] = []
    expired = 0
    position: Position | None = None
    trades = []
    equity = []
    realized = 0.0
    fee = settings.roundtrip_cost_per_ounce * settings.ounces
    previous: pd.Timestamp | None = None

    def exit_trade(at: pd.Timestamp, price: float, reason: str) -> None:
        nonlocal realized, position
        p = position
        assert p is not None
        gross = p.side * (price - p.entry_price) * settings.ounces
        net = gross - fee
        realized += net
        trades.append({
            "strategy": p.strategy, "signal_at": p.signal_at,
            "entry_at": p.entry_at, "closed_at": at, "side": p.side,
            "entry_price": p.entry_price, "exit_price": price,
            "stop": p.stop, "target": p.target, "ounces": settings.ounces,
            "gross_pnl": gross, "cost": fee, "net_pnl": net,
            "exit_reason": reason, "gap_minutes": p.gap_minutes,
        })
        position = None

    for when, bar in minutes.iterrows():
        at = pd.Timestamp(when)
        op, hi, lo, cl = [float(bar[k]) for k in ("o", "h", "l", "c")]
        if not np.isfinite([op, hi, lo, cl]).all() or lo <= 0 or lo > min(op, cl) or hi < max(op, cl):
            raise ValueError(f"Invalid M1 OHLC {at}")
        missing = max(0, int((at - previous).total_seconds() / 60) - 1) if previous is not None else 0
        previous = at
        occupied_at_open = position is not None

        # Process old open position at first observed quote after a gap.
        if position is not None:
            position.gap_minutes += missing
            if (position.side == 1 and op <= position.stop) or (
                position.side == -1 and op >= position.stop
            ):
                exit_trade(at, op, "gap_stop" if missing else "open_stop")
            elif (position.side == 1 and op >= position.target) or (
                position.side == -1 and op <= position.target
            ):
                exit_trade(at, position.target, "open_target")

        # Activate only orders already placed on a COMPLETED candle.
        while cursor < len(queued) and pd.Timestamp(queued[cursor].placed_at) <= at:
            pending.append(queued[cursor])
            cursor += 1
        still_pending = []
        for o in pending:
            if pd.Timestamp(o.expires_at) < at:
                expired += 1
            else:
                still_pending.append(o)
        pending = still_pending

        # Oldest eligible pending order wins. Existing positions block entry.
        # No opening a second position on the same minute another position exited.
        if not occupied_at_open and position is None:
            for j, o in enumerate(pending):
                touched = lo <= o.price if o.side == 1 else hi >= o.price
                if not touched:
                    continue
                position = Position(
                    entry_at=at, signal_at=pd.Timestamp(o.placed_at),
                    side=o.side, entry_price=o.price,
                    stop=o.stop, target=o.target, strategy=o.strategy,
                )
                pending.pop(j)
                # Drop other pending orders once a position opens, so a stale
                # order cannot enter after this position eventually closes.
                expired += len(pending)
                pending.clear()
                # Conservative first-price fill if the market opened beyond
                # the stop, rather than magical fill at original SL.
                if (o.side == 1 and op <= o.stop) or (o.side == -1 and op >= o.stop):
                    exit_trade(at, op, "entry_open_beyond_stop")
                break

        if position is not None:
            hit_stop = lo <= position.stop if position.side == 1 else hi >= position.stop
            hit_target = hi >= position.target if position.side == 1 else lo <= position.target
            if hit_stop:
                exit_trade(at, position.stop, "ambiguous_stop_first" if hit_target else "stop")
            elif hit_target:
                exit_trade(at, position.target, "target")

        floating = (
            position.side * (cl - position.entry_price) * settings.ounces - fee
            if position is not None else 0.0
        )
        equity.append({
            "at": at, "realized_pnl": realized,
            "floating_pnl": floating, "equity": realized + floating,
        })

    if position is not None and settings.close_at_end:
        exit_trade(pd.Timestamp(minutes.index[-1]), float(minutes["c"].iloc[-1]), "end_of_data")
        equity[-1]["realized_pnl"] = realized
        equity[-1]["floating_pnl"] = 0.0
        equity[-1]["equity"] = realized

    columns = [
        "strategy", "signal_at", "entry_at", "closed_at", "side",
        "entry_price", "exit_price", "stop", "target", "ounces",
        "gross_pnl", "cost", "net_pnl", "exit_reason", "gap_minutes",
    ]
    return Result(
        trades=pd.DataFrame.from_records(trades, columns=columns),
        equity=pd.DataFrame.from_records(equity).set_index("at"),
        pending_at_end=len(pending) + len(queued) - cursor,
        expired_signals=expired,
    )
