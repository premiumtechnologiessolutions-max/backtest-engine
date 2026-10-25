"""Causal Market + Limit replay on one shared M1 portfolio ledger.

Opening Market orders compete with limits already marketable at the open.
Limits requiring a later intrabar touch consume only the remaining capacity:
an unknowable future low/high cannot displace an opening Market trade.
This is a conservative OHLC research model, not broker execution or margin.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from numbers import Integral
from typing import Sequence

import numpy as np
import pandas as pd

from .limit_engine import LimitOrder
from .model import Signal
from .portfolio import (
    PortfolioResult, PortfolioSettings, validate_portfolio, write_portfolio_report,
)


@dataclass
class UnifiedPortfolioResult(PortfolioResult):
    uncertain_entry_tp_deferred: int = 0


@dataclass(frozen=True)
class _Instruction:
    available_at: pd.Timestamp
    strategy: str
    input_order: int
    payload: Signal | LimitOrder
    expires_at: pd.Timestamp | None = None

    @property
    def priority(self) -> tuple:
        return self.available_at, self.strategy, self.input_order


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
    order_type: str
    gap_minutes: int = 0


def run_unified_portfolio(
    minutes: pd.DataFrame,
    signals: Sequence[Signal],
    orders: Sequence[LimitOrder],
    settings: PortfolioSettings,
) -> UnifiedPortfolioResult:
    """Execute Market and Limit instructions with shared frozen capacity.

    Signals/placements denote information already available at that timestamp.
    Subminute confirmation can enter only at the next observed minute open.
    At each M1 open, slots/ounces held by existing positions stay reserved for
    the whole bar even if an exit occurs. Within each known execution phase,
    priority is (confirmation, strategy, input order), never future profit.
    A touched order rejected for capacity is discarded once. A strategy may
    hold one position; filling cancels its other pending instructions. Limits
    fill at their specified price without beneficial gap improvement, with
    adverse opening gaps exiting at the observed open. All Limit entry-bar
    targets are deferred because OHLC does not establish the post-fill path.
    Limit expiration is inclusive on the observed M1 opening clock, matching
    the standalone reference; it does not model intraminute cancellation.
    """
    if settings.all_in_cost_per_ounce != 0.40:
        raise ValueError("Unified research fixes ALL-IN fee at $0.40/oz per roundtrip")
    if (isinstance(settings.max_open_positions, bool) or
            not isinstance(settings.max_open_positions, Integral) or
            settings.max_open_positions < 1):
        raise ValueError("Shared position capacity must be a positive integer")
    if not math.isfinite(settings.max_total_ounces) or settings.max_total_ounces <= 0:
        raise ValueError("Shared ounce capacity must be finite positive")
    if not settings.ounces_by_strategy or any(
        not isinstance(name, str) or not name or not math.isfinite(float(quantity)) or float(quantity) <= 0
        for name, quantity in settings.ounces_by_strategy.items()
    ):
        raise ValueError("Each strategy needs a finite positive ounce allocation")
    if (isinstance(settings.max_entry_delay_minutes, bool) or
            not isinstance(settings.max_entry_delay_minutes, Integral) or
            settings.max_entry_delay_minutes < 0):
        raise ValueError("Entry delay must be a finite nonnegative integer")
    holding = settings.max_holding_minutes
    if holding is not None and (isinstance(holding, bool) or not isinstance(holding, Integral) or holding <= 0):
        raise ValueError("Holding duration must be a finite positive integer")
    if minutes.empty or not isinstance(minutes.index, pd.DatetimeIndex):
        raise ValueError("Nonempty M1 DatetimeIndex required")
    if (minutes.index.tz is None or minutes.index.hasnans or
            minutes.index.has_duplicates or not minutes.index.is_monotonic_increasing):
        raise ValueError("M1 index must be timezone-aware, sorted and unique")
    if (minutes.index.as_unit("ns").asi8 % 60_000_000_000 != 0).any():
        raise ValueError("M1 timestamps must align to minute opens")
    if not {"o", "h", "l", "c"}.issubset(minutes):
        raise ValueError("M1 OHLC required")
    quotes = minutes[["o", "h", "l", "c"]].to_numpy(dtype=float)
    if not np.isfinite(quotes).all():
        raise ValueError("Invalid source M1 OHLC")
    op_all, hi_all, lo_all, cl_all = quotes.T
    if ((lo_all <= 0) | (lo_all > np.minimum(op_all, cl_all)) |
            (hi_all < np.maximum(op_all, cl_all))).any():
        raise ValueError("Invalid source M1 OHLC")

    queue = []
    for number, payload in enumerate([*signals, *orders]):
        expected = Signal if number < len(signals) else LimitOrder
        if not isinstance(payload, expected):
            raise TypeError(f"Expected {expected.__name__}")
        if payload.strategy not in settings.ounces_by_strategy:
            raise ValueError(f"Missing allocation for {payload.strategy!r}")
        timestamp = payload.confirmed_at if isinstance(payload, Signal) else payload.placed_at
        available = pd.Timestamp(timestamp)
        expires = pd.Timestamp(payload.expires_at) if isinstance(payload, LimitOrder) else None
        if pd.isna(available) or available.tzinfo is None:
            raise ValueError("Instruction timestamp must be finite and timezone-aware")
        if expires is not None and (pd.isna(expires) or expires.tzinfo is None or expires < available):
            raise ValueError("Invalid timezone-aware limit expiry")
        queue.append(_Instruction(
            available.tz_convert("UTC"), payload.strategy, number, payload,
            expires.tz_convert("UTC") if expires is not None else None,
        ))
    queue.sort(key=lambda item: item.priority)

    positions: dict[str, _Position] = {}
    pending: list[_Instruction] = []
    pointer = expired = rejected_capacity = rejected_duplicate = deferred_tp = 0
    realized = 0.0
    trades, equity = [], []
    previous: pd.Timestamp | None = None

    def close_position(position: _Position, at: pd.Timestamp, price: float, reason: str) -> None:
        nonlocal realized
        gross = position.side * (price - position.entry_price) * position.ounces
        fee = position.ounces * settings.all_in_cost_per_ounce
        net = gross - fee
        realized += net
        trades.append({
            "strategy": position.strategy, "signal_at": position.signal_at,
            "entry_at": position.entry_at, "closed_at": at, "side": position.side,
            "entry_price": position.entry_price, "exit_price": price,
            "stop": position.stop, "target": position.target,
            "ounces": position.ounces, "gross_pnl": gross, "cost": fee,
            "net_pnl": net, "exit_reason": reason,
            "gap_minutes": position.gap_minutes, "order_type": position.order_type,
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
        entered: set[str] = set()

        # Existing gaps are evaluated at the first observable price; capital
        # released here remains unavailable until the next observed minute.
        for position in list(positions.values()):
            position.gap_minutes += missing
            if ((position.side == 1 and op <= position.stop) or
                    (position.side == -1 and op >= position.stop)):
                close_position(position, at, op, "gap_stop" if missing else "open_stop")
            elif ((position.side == 1 and op >= position.target) or
                    (position.side == -1 and op <= position.target)):
                close_position(position, at, position.target, "open_target")
            elif holding is not None and at >= position.entry_at + pd.Timedelta(minutes=holding):
                # Scheduled time exits observe only the opening quote, before
                # the later high/low. Gaps cannot create a fabricated fill at
                # an unobserved scheduled minute.
                close_position(position, at, op, "time_exit")

        opening: list[_Instruction] = []
        while pointer < len(queue) and queue[pointer].available_at <= at:
            instruction = queue[pointer]
            pointer += 1
            if isinstance(instruction.payload, Signal):
                delay = (at - instruction.available_at).total_seconds() / 60
                if delay > settings.max_entry_delay_minutes:
                    expired += 1
                else:
                    opening.append(instruction)
            else:
                pending.append(instruction)

        intrabar: list[_Instruction] = []
        for instruction in pending:
            order = instruction.payload
            assert isinstance(order, LimitOrder)
            if instruction.expires_at < at:
                expired += 1
            elif instruction.strategy in occupied_at_open:
                rejected_duplicate += 1
            elif (order.side == 1 and op <= order.price) or (order.side == -1 and op >= order.price):
                opening.append(instruction)
            else:
                intrabar.append(instruction)
        # Pending activation and original input order must not influence the
        # common opening clock. Untouched older limits cannot outrank it.
        opening.sort(key=lambda item: item.priority)
        intrabar.sort(key=lambda item: item.priority)

        def enter(instruction: _Instruction) -> None:
            nonlocal slots, remaining_ounces, rejected_capacity, rejected_duplicate
            name, payload = instruction.strategy, instruction.payload
            if name in occupied_at_open or name in entered:
                rejected_duplicate += 1
                return
            quantity = float(settings.ounces_by_strategy[name])
            if slots <= 0 or quantity > remaining_ounces + 1e-12:
                rejected_capacity += 1
                return
            slots -= 1
            remaining_ounces -= quantity
            entered.add(name)
            if isinstance(payload, Signal):
                price = op
                stop = op - payload.side * payload.stop_distance
                target = op + payload.side * payload.target_distance
                kind = "market"
            else:
                price, stop, target = map(float, (payload.price, payload.stop, payload.target))
                kind = "limit"
            position = _Position(name, instruction.available_at, at, payload.side,
                                 quantity, price, stop, target, kind)
            positions[name] = position
            if kind == "limit" and ((position.side == 1 and op <= stop) or
                                    (position.side == -1 and op >= stop)):
                close_position(position, at, op, "entry_open_beyond_stop")

        for instruction in opening:
            enter(instruction)
        next_pending = []
        for instruction in intrabar:
            order = instruction.payload
            if instruction.strategy in entered:
                rejected_duplicate += 1
            elif (order.side == 1 and lo <= order.price) or (order.side == -1 and hi >= order.price):
                enter(instruction)
            else:
                next_pending.append(instruction)
        pending = []
        for instruction in next_pending:
            if instruction.strategy in entered:
                rejected_duplicate += 1
            else:
                pending.append(instruction)

        for position in list(positions.values()):
            stop_hit = lo <= position.stop if position.side == 1 else hi >= position.stop
            target_hit = hi >= position.target if position.side == 1 else lo <= position.target
            if stop_hit:
                close_position(position, at, position.stop,
                               "ambiguous_stop_first" if target_hit else "stop")
            elif target_hit:
                if position.strategy in entered and position.order_type == "limit":
                    deferred_tp += 1
                else:
                    close_position(position, at, position.target, "target")

        floating = sum(p.side * (cl - p.entry_price) * p.ounces
                       - p.ounces * settings.all_in_cost_per_ounce
                       for p in positions.values())
        equity.append({
            "at": at, "realized_pnl": realized, "floating_pnl": floating,
            "equity": realized + floating, "open_positions": len(positions),
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
        "gross_pnl", "cost", "net_pnl", "exit_reason", "gap_minutes", "order_type",
    ]
    result = UnifiedPortfolioResult(
        trades=pd.DataFrame.from_records(trades, columns=columns),
        equity=pd.DataFrame.from_records(equity).set_index("at"),
        pending_at_end=len(pending) + len(queue) - pointer,
        expired_signals=expired, capacity_rejected=rejected_capacity,
        duplicate_strategy_rejected=rejected_duplicate,
        open_positions_at_end=open_at_end,
        uncertain_entry_tp_deferred=deferred_tp,
    )
    validate_portfolio(result, settings)
    return result


def write_unified_portfolio_report(
    result: UnifiedPortfolioResult, settings: PortfolioSettings, out: str | Path,
) -> dict:
    """Write reconciled M1 equity, trades, weekly and monthly shared reports."""
    summary = write_portfolio_report(result, settings, out)
    summary.update(
        uncertain_entry_tp_deferred=result.uncertain_entry_tp_deferred,
        execution_policy=(
            "Opening Market and marketable Limit instructions have confirmation/strategy/input "
            "priority; later Limit touches use remaining frozen capacity. Stop-first, "
            "adverse gap-through, Limit entry-bar TP deferred, inclusive expiry at "
            "observed minute opens, no same-M1 slot recycling."
        ),
    )
    (Path(out) / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
