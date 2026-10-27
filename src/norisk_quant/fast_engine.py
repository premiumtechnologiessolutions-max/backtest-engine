"""Optimized exact M1 OHLC research replay; NOT broker tick execution.

For signal types supported by this version: confirmed market entry at the
next observed M1 open (within max_entry_delay_minutes), one open position,
SL-first M1 ambiguity, adverse gap-through stops, $0.40/oz ALL-IN cost.

No fabricated ticks or fills within missing intervals. Returns the same
Result/trade columns as execution.run for parity testing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .execution import Result
from .model import Position, Settings, Signal


def run_fast(minutes: pd.DataFrame, signals: list[Signal], settings: Settings) -> Result:
    if minutes.empty or not isinstance(minutes.index, pd.DatetimeIndex):
        raise ValueError("Nonempty M1 DatetimeIndex required")
    if (minutes.index.tz is None or str(minutes.index.tz) != "UTC"
            or minutes.index.has_duplicates or not minutes.index.is_monotonic_increasing):
        raise ValueError("M1 DatetimeIndex must be UTC, sorted, and unique")
    for required in ("o", "h", "l", "c"):
        if required not in minutes:
            raise ValueError(f"Missing {required}")
    for s in signals:
        if pd.Timestamp(s.confirmed_at).tzinfo is None:
            raise ValueError("Signal confirmation must include timezone")
    # .asi8 reflects the stored datetime unit, not necessarily nanoseconds.
    # Convert second/millisecond/microsecond UTC indexes to canonical ns
    # before M1 alignment, signal causality and gap calculations.
    if minutes.index.unit != "ns":
        minutes = minutes.copy(deep=False)
        minutes.index = minutes.index.as_unit("ns")
    stamps_ns = minutes.index.asi8
    if (stamps_ns % 60_000_000_000 != 0).any():
        raise ValueError("M1 candle opens must align to exact minute boundaries")
    stamps = stamps_ns // 1_000_000_000
    opens, highs, lows, closes = (
        minutes[k].to_numpy(dtype=np.float64) for k in ("o", "h", "l", "c")
    )
    if (
        not np.isfinite(np.column_stack((opens, highs, lows, closes))).all()
        or (lows > np.minimum(opens, closes)).any()
        or (highs < np.maximum(opens, closes)).any()
        or (highs < lows).any()
        or (lows <= 0).any()
    ):
        raise ValueError("Invalid M1 OHLC")
    ordered = sorted(signals, key=lambda s: pd.Timestamp(s.confirmed_at))
    # Nanosecond confirmation time preserves subsecond causality. Truncating
    # to int(epoch_seconds) could execute a signal up to 0.999s BEFORE it existed.
    sig_times_ns = [
        pd.Timestamp(s.confirmed_at).tz_convert("UTC").value
        for s in ordered
    ]
    pos: Position | None = None
    pointer = expired = 0
    fee = settings.roundtrip_cost_per_ounce * settings.ounces
    realized = 0.0
    ledger: list[dict] = []
    # Preserve every observed M1 mark without millions of Python dicts and
    # Timestamp objects. Continuous multi-year design runs need bounded
    # per-bar storage, not an annual reset that force-closes real positions.
    realized_samples = np.empty(len(minutes), dtype=np.float64)
    floating_samples = np.empty(len(minutes), dtype=np.float64)
    previous: int | None = None

    def close(trade: Position, when: int, price: float, reason: str) -> None:
        nonlocal realized
        net_gross = trade.side * (price - trade.entry_price) * settings.ounces
        pnl = net_gross - fee
        realized += pnl
        ledger.append({
            "strategy": trade.strategy,
            "signal_at": trade.signal_at,
            "entry_at": trade.entry_at,
            "closed_at": pd.Timestamp(when, unit="s", tz="UTC"),
            "side": trade.side,
            "entry_price": trade.entry_price,
            "exit_price": price,
            "stop": trade.stop,
            "target": trade.target,
            "ounces": settings.ounces,
            "gross_pnl": net_gross,
            "cost": fee,
            "net_pnl": pnl,
            "exit_reason": reason,
            "gap_minutes": trade.gap_minutes,
        })

    for i, now_raw in enumerate(stamps):
        now = int(now_raw)
        op, hi, lo, cl = opens[i], highs[i], lows[i], closes[i]
        gap = max(0, (now - previous) // 60 - 1) if previous is not None else 0
        previous = now
        occupied = pos is not None
        if pos is not None:
            pos.gap_minutes += gap
            if (pos.side == 1 and op <= pos.stop) or (pos.side == -1 and op >= pos.stop):
                close(pos, now, op, "gap_stop" if gap else "open_stop")
                pos = None
            elif (pos.side == 1 and op >= pos.target) or (pos.side == -1 and op <= pos.target):
                close(pos, now, pos.target, "open_target")
                pos = None
            elif (
                settings.max_holding_minutes is not None
                and now - int(pd.Timestamp(pos.entry_at).timestamp())
                >= settings.max_holding_minutes * 60
            ):
                close(pos, now, op, "time_exit")
                pos = None
        while pointer < len(ordered) and (
            int(stamps_ns[i]) - sig_times_ns[pointer]
        ) > settings.max_entry_delay_minutes * 60_000_000_000:
            expired += 1
            pointer += 1
        if (
            not occupied and pos is None and pointer < len(ordered)
            and int(stamps_ns[i]) >= sig_times_ns[pointer]
        ):
            sig = ordered[pointer]
            pointer += 1
            pos = Position(
                entry_at=pd.Timestamp(now, unit="s", tz="UTC"),
                signal_at=pd.Timestamp(sig.confirmed_at).tz_convert("UTC"),
                side=sig.side,
                entry_price=float(op),
                stop=float(op - sig.side * sig.stop_distance),
                target=float(op + sig.side * sig.target_distance),
                strategy=sig.strategy,
            )
        if pos is not None:
            stop_hit = lo <= pos.stop if pos.side == 1 else hi >= pos.stop
            target_hit = hi >= pos.target if pos.side == 1 else lo <= pos.target
            if stop_hit:
                close(pos, now, pos.stop, "ambiguous_stop_first" if target_hit else "stop")
                pos = None
            elif target_hit:
                close(pos, now, pos.target, "target")
                pos = None
        floating = (
            pos.side * (cl - pos.entry_price) * settings.ounces - fee
            if pos is not None else 0.0
        )
        realized_samples[i] = realized
        floating_samples[i] = floating

    if pos is not None and settings.close_at_end:
        close(pos, int(stamps[-1]), float(closes[-1]), "end_of_data")
        realized_samples[-1] = realized
        floating_samples[-1] = 0.0

    columns = [
        "strategy", "signal_at", "entry_at", "closed_at", "side",
        "entry_price", "exit_price", "stop", "target", "ounces",
        "gross_pnl", "cost", "net_pnl", "exit_reason", "gap_minutes",
    ]
    return Result(
        trades=pd.DataFrame.from_records(ledger, columns=columns),
        equity=pd.DataFrame({
            "realized_pnl": realized_samples,
            "floating_pnl": floating_samples,
            "equity": realized_samples + floating_samples,
        }, index=pd.DatetimeIndex(
            pd.to_datetime(stamps_ns, unit="ns", utc=True), name="at",
        )),
        pending_at_end=len(ordered) - pointer,
        expired_signals=expired,
    )
