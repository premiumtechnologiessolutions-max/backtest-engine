"""Shared-capacity, conservative M1 OHLC replay of multiple LIMIT strategies.

Not a tick path or broker fill/margin model. Fixed all-in cost: $0.40/oz
for each roundtrip, charged once. Open positions carry across missing bars.
No same-minute slot recycling, no entry before a completed signal, stop-first
intrabar, and no same-entry-bar target award without a known price path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from .limit_engine import LimitOrder
from .portfolio import PortfolioResult, PortfolioSettings, validate_portfolio


@dataclass
class LimitPortfolioResult(PortfolioResult):
    uncertain_entry_tp_deferred: int = 0


@dataclass
class _Position:
    strategy: str
    signal_at: pd.Timestamp
    entry_at: pd.Timestamp
    side: int
    ounces: float
    entry_price: float
    stop: float
    target: float
    gap_minutes: int = 0


def run_limit_portfolio(
    minutes: pd.DataFrame,
    orders: Sequence[LimitOrder],
    settings: PortfolioSettings,
) -> LimitPortfolioResult:
    """Replay pre-confirmed LIMIT orders with deterministic shared capacity.

    On a touch with insufficient opening capacity, the order is rejected once
    (not repeatedly re-tried). Orders for a strategy with an already-open
    position are discarded, and other pending orders for a just-filled
    strategy are cancelled. Ties: placed_at, strategy, original input order.
    This policy is intentionally distinct from independently summing P/L.
    """
    if minutes.empty or not isinstance(minutes.index, pd.DatetimeIndex):
        raise ValueError("Nonempty M1 DatetimeIndex required")
    if minutes.index.tz is None or minutes.index.has_duplicates or not minutes.index.is_monotonic_increasing:
        raise ValueError("M1 index must be timezone-aware, unique and sorted")
    if (minutes.index.asi8 % 60_000_000_000 != 0).any():
        raise ValueError("M1 timestamps must align to minute opens")
    if not {"o", "h", "l", "c"}.issubset(minutes.columns):
        raise ValueError("M1 OHLC required")
    quotes = minutes[["o", "h", "l", "c"]].to_numpy(dtype=float)
    if not np.isfinite(quotes).all():
        raise ValueError("Invalid M1 price")
    op_all, hi_all, lo_all, cl_all = quotes.T
    if ((lo_all <= 0) | (lo_all > np.minimum(op_all, cl_all)) |
            (hi_all < np.maximum(op_all, cl_all))).any():
        raise ValueError("Invalid M1 OHLC ranges")

    queue = []
    for number, order in enumerate(orders):
        if not isinstance(order, LimitOrder):
            raise TypeError("Expected LimitOrder")
        if order.strategy not in settings.ounces_by_strategy:
            raise ValueError(f"Missing allocation for {order.strategy!r}")
        placed = pd.Timestamp(order.placed_at)
        expires = pd.Timestamp(order.expires_at)
        if placed.tzinfo is None or expires.tzinfo is None:
            raise ValueError("Limit timestamps must have a timezone")
        queue.append((placed.tz_convert("UTC"), order.strategy, number,
                      expires.tz_convert("UTC"), order))
    queue.sort(key=lambda item: item[:3])
    positions: dict[str, _Position] = {}
    pending = []
    pointer = expired = rejected_capacity = rejected_duplicate = deferred_tp = 0
    trades = []
    equity = []
    realized = 0.0
    previous: pd.Timestamp | None = None

    def close_position(position: _Position, at: pd.Timestamp, price: float, reason: str) -> None:
        nonlocal realized
        gross = position.side * (price - position.entry_price) * position.ounces
        fee = position.ounces * settings.all_in_cost_per_ounce
        net = gross - fee
        realized += net
        trades.append({
            "strategy": position.strategy, "signal_at": position.signal_at,
            "entry_at": position.entry_at, "closed_at": at,
            "side": position.side, "entry_price": position.entry_price,
            "exit_price": price, "stop": position.stop,
            "target": position.target, "ounces": position.ounces,
            "gross_pnl": gross, "cost": fee, "net_pnl": net,
            "exit_reason": reason, "gap_minutes": position.gap_minutes,
        })
        del positions[position.strategy]

    for index, timestamp in enumerate(minutes.index):
        at = pd.Timestamp(timestamp).tz_convert("UTC")
        op, hi, lo, cl = map(float, quotes[index])
        missing = max(0, (at.value - previous.value) // 60_000_000_000 - 1) if previous is not None else 0
        previous = at
        occupied_at_open = set(positions)
        slots = settings.max_open_positions - len(positions)
        remaining_ounces = settings.max_total_ounces - sum(p.ounces for p in positions.values())

        for position in list(positions.values()):
            position.gap_minutes += missing
            if ((position.side == 1 and op <= position.stop) or
                    (position.side == -1 and op >= position.stop)):
                close_position(position, at, op, "gap_stop" if missing else "open_stop")
            elif ((position.side == 1 and op >= position.target) or
                    (position.side == -1 and op <= position.target)):
                close_position(position, at, position.target, "open_target")

        while pointer < len(queue) and queue[pointer][0] <= at:
            pending.append(queue[pointer])
            pointer += 1
        eligible = []
        for item in pending:
            placed, name, number, expires, order = item
            if expires < at:
                expired += 1
            elif name in occupied_at_open or name in positions:
                rejected_duplicate += 1
            else:
                eligible.append(item)
        pending = eligible

        entered = set()
        next_pending = []
        for item in pending:
            placed, name, number, expires, order = item
            if name in entered:
                rejected_duplicate += 1
                continue
            touched = lo <= order.price if order.side == 1 else hi >= order.price
            if not touched:
                next_pending.append(item)
                continue
            qty = float(settings.ounces_by_strategy[name])
            if slots <= 0 or qty > remaining_ounces + 1e-12:
                rejected_capacity += 1
                continue
            slots -= 1
            remaining_ounces -= qty
            entered.add(name)
            position = _Position(
                strategy=name, signal_at=placed, entry_at=at,
                side=order.side, ounces=qty, entry_price=float(order.price),
                stop=float(order.stop), target=float(order.target),
            )
            positions[name] = position
            if ((position.side == 1 and op <= position.stop) or
                    (position.side == -1 and op >= position.stop)):
                close_position(position, at, op, "entry_open_beyond_stop")
        # Cancel other pending orders from a newly filled strategy; no
        # same-minute re-entry even if it stopped immediately.
        pending = []
        for item in next_pending:
            if item[1] in entered:
                rejected_duplicate += 1
            else:
                pending.append(item)

        for position in list(positions.values()):
            hit_stop = lo <= position.stop if position.side == 1 else hi >= position.stop
            hit_target = hi >= position.target if position.side == 1 else lo <= position.target
            if hit_stop:
                close_position(position, at, position.stop,
                               "ambiguous_stop_first" if hit_target else "stop")
            elif hit_target:
                if position.strategy in entered:
                    deferred_tp += 1
                else:
                    close_position(position, at, position.target, "target")

        floating = sum(
            p.side * (cl - p.entry_price) * p.ounces
            - p.ounces * settings.all_in_cost_per_ounce
            for p in positions.values()
        )
        equity.append({
            "at": at, "realized_pnl": realized, "floating_pnl": floating,
            "equity": realized + floating,
            "open_positions": len(positions),
            "gross_open_ounces": sum(p.ounces for p in positions.values()),
        })

    open_at_end = len(positions)
    if positions and settings.close_at_end:
        at = pd.Timestamp(minutes.index[-1]).tz_convert("UTC")
        for position in list(positions.values()):
            close_position(position, at, float(cl_all[-1]), "end_of_data")
        equity[-1].update(realized_pnl=realized, floating_pnl=0.0,
                          equity=realized, open_positions=0, gross_open_ounces=0.0)

    columns = [
        "strategy", "signal_at", "entry_at", "closed_at", "side",
        "entry_price", "exit_price", "stop", "target", "ounces",
        "gross_pnl", "cost", "net_pnl", "exit_reason", "gap_minutes",
    ]
    result = LimitPortfolioResult(
        trades=pd.DataFrame.from_records(trades, columns=columns),
        equity=pd.DataFrame.from_records(equity).set_index("at"),
        pending_at_end=len(pending) + len(queue) - pointer,
        expired_signals=expired,
        capacity_rejected=rejected_capacity,
        duplicate_strategy_rejected=rejected_duplicate,
        open_positions_at_end=open_at_end,
        uncertain_entry_tp_deferred=deferred_tp,
    )
    validate_portfolio(result, settings)
    return result
