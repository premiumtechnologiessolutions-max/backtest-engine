from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import math

import pandas as pd

from .model import Position, Settings, Signal


@dataclass
class Result:
    trades: pd.DataFrame
    equity: pd.DataFrame
    pending_at_end: int
    expired_signals: int = 0
    uncertain_entry_tp_deferred: int = 0


def run(minutes: pd.DataFrame, signals: Iterable[Signal], settings: Settings) -> Result:
    """M1 OHLC research simulator, next available open, stop-first intrabar.

    Both sides use BID OHLC as a SYNTHETIC reference quote. A single fixed
    round-trip fee replaces, rather than supplements, spread/commission.
    This is not an executable broker fill model or tick reconstruction.
    """
    if minutes.empty:
        raise ValueError("No minute bars")
    if not isinstance(minutes.index, pd.DatetimeIndex) or minutes.index.tz is None:
        raise ValueError("Market data needs timezone-aware UTC DatetimeIndex")
    if minutes.index.has_duplicates or not minutes.index.is_monotonic_increasing:
        raise ValueError("M1 index must be sorted and unique")
    if (minutes.index.asi8 % 60_000_000_000 != 0).any():
        raise ValueError("M1 candle opens must align to exact minute boundaries")
    required = {"o", "h", "l", "c"}
    if not required.issubset(minutes):
        raise ValueError("Market data missing OHLC columns")

    ordered = sorted(signals, key=lambda signal: pd.Timestamp(signal.confirmed_at))
    cost = settings.roundtrip_cost_per_ounce * settings.ounces
    trades: list[dict] = []
    equity: list[dict] = []
    index = 0
    position: Position | None = None
    realized = 0.0
    prev_time = None
    skipped = 0

    def close(position: Position, at: pd.Timestamp, price: float, reason: str) -> None:
        nonlocal realized
        gross = position.side * (price - position.entry_price) * settings.ounces
        net = gross - cost
        realized += net
        trades.append(
            {
                "strategy": position.strategy,
                "signal_at": position.signal_at,
                "entry_at": position.entry_at,
                "closed_at": at,
                "side": position.side,
                "entry_price": position.entry_price,
                "exit_price": price,
                "stop": position.stop,
                "target": position.target,
                "ounces": settings.ounces,
                "gross_pnl": gross,
                "cost": cost,
                "net_pnl": net,
                "exit_reason": reason,
                "gap_minutes": position.gap_minutes,
            }
        )

    for timestamp, bar in minutes.iterrows():
        start = pd.Timestamp(timestamp)
        gap = (
            max(0, round((start - prev_time).total_seconds() / 60) - 1)
            if prev_time is not None
            else 0
        )
        prev_time = start
        occupied_at_open = position is not None
        op, hi, lo, cl = (float(bar[k]) for k in ("o", "h", "l", "c"))
        if (
            not all(math.isfinite(price) for price in (op, hi, lo, cl))
            or lo <= 0 or not (lo <= op <= hi and lo <= cl <= hi)
        ):
            raise ValueError(f"Bad OHLC at {start}")

        # The first available quote after an unobserved gap is the earliest
        # price that can be justified. A stop may fill worse than its level.
        if position is not None:
            position.gap_minutes += gap
            if position.side == 1 and op <= position.stop:
                close(position, start, op, "gap_stop" if gap else "open_stop")
                position = None
            elif position.side == -1 and op >= position.stop:
                close(position, start, op, "gap_stop" if gap else "open_stop")
                position = None
            elif position.side == 1 and op >= position.target:
                close(position, start, position.target, "open_target")
                position = None
            elif position.side == -1 and op <= position.target:
                close(position, start, position.target, "open_target")
                position = None
            elif (
                settings.max_holding_minutes is not None
                and start - pd.Timestamp(position.entry_at)
                >= pd.Timedelta(minutes=settings.max_holding_minutes)
            ):
                # Stops/targets already breached at the observed open take
                # precedence. A scheduled exit precedes this candle's range.
                close(position, start, op, "time_exit")
                position = None

        # Expire stale signals, rather than acting on an old signal after a
        # market closure. Signals are confirmed at CLOSE, not earlier.
        while index < len(ordered):
            elapsed = (start - pd.Timestamp(ordered[index].confirmed_at)).total_seconds() / 60
            if elapsed > settings.max_entry_delay_minutes:
                skipped += 1
                index += 1
            else:
                break

        # No same-minute replacement after an old trade exits. No multiple
        # overlapping positions. Intrabar decision is evaluated after entry.
        if not occupied_at_open and position is None:
            while index < len(ordered):
                item = ordered[index]
                confirmed = pd.Timestamp(item.confirmed_at)
                if confirmed > start:
                    break
                index += 1
                if start < confirmed:
                    continue
                if item.side == 1:
                    stop, target = op - item.stop_distance, op + item.target_distance
                else:
                    stop, target = op + item.stop_distance, op - item.target_distance
                position = Position(
                    entry_at=start,
                    # Normalize explicit-offset signals to canonical UTC so
                    # reference and fast ledgers have identical timezone dtypes.
                    signal_at=confirmed.tz_convert("UTC"),
                    side=item.side,
                    entry_price=op,
                    stop=stop,
                    target=target,
                    strategy=item.strategy,
                )
                break

        if position is not None:
            stop_hit = lo <= position.stop if position.side == 1 else hi >= position.stop
            target_hit = hi >= position.target if position.side == 1 else lo <= position.target
            if stop_hit:
                # When both SL and TP are inside one M1 candle, assume SL first.
                reason = "ambiguous_stop_first" if target_hit else "stop"
                close(position, start, position.stop, reason)
                position = None
            elif target_hit:
                close(position, start, position.target, "target")
                position = None

        floating = (
            position.side * (cl - position.entry_price) * settings.ounces - cost
            if position is not None
            else 0.0
        )
        equity.append(
            {"at": start, "realized_pnl": realized, "floating_pnl": floating, "equity": realized + floating}
        )

    if position is not None and settings.close_at_end:
        last_at = pd.Timestamp(minutes.index[-1])
        last_close = float(minutes["c"].iloc[-1])
        close(position, last_at, last_close, "end_of_data")
        position = None
        equity[-1]["realized_pnl"] = realized
        equity[-1]["floating_pnl"] = 0.0
        equity[-1]["equity"] = realized

    trade_cols = [
        "strategy", "signal_at", "entry_at", "closed_at", "side",
        "entry_price", "exit_price", "stop", "target", "ounces", "gross_pnl",
        "cost", "net_pnl", "exit_reason", "gap_minutes",
    ]
    return Result(
        trades=pd.DataFrame.from_records(trades, columns=trade_cols),
        equity=pd.DataFrame.from_records(equity).set_index("at"),
        pending_at_end=len(ordered) - index,
        expired_signals=skipped,
    )
