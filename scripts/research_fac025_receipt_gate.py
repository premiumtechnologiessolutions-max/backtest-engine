"""FAC025 research-only receipt-time preflight for observed M1 and closed trades.

This adapter requires independently captured UTC receipt/confirmation times.
It does NOT authenticate timestamps or certify broker feed latency, fills, or
profitability. No raw quote data, strategy execution, or trading orders.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from scripts.research_fac025_observed_m15 import (
        MAX_INPUT_M1, evaluate_gate_from_observed_m1,
    )
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from research_fac025_observed_m15 import (
        MAX_INPUT_M1, evaluate_gate_from_observed_m1,
    )

M1_FIELDS = frozenset({"open_at", "open", "high", "low", "close", "received_at"})
TRADE_FIELDS = frozenset({"closed_at", "net_usd_per_oz", "confirmed_at"})
MAX_CONFIRMED_TRADES = 100_000
MINUTE = timedelta(minutes=1)


def _utc(value: object, label: str) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise ValueError(f"{label} must be UTC-aware datetime")
    return value.astimezone(timezone.utc)


def evaluate_gate_from_received_inputs(
    signal_at: datetime,
    received_m1: list[dict],
    confirmed_trades: list[dict],
    *,
    lookback: int = 4,
    **frozen_gate_parameters: object,
) -> dict:
    """Reject M1/trade information not demonstrably received BEFORE signal.

    M1.open_at is the minute OPEN; a completed OHLC cannot be received before
    open_at + 1 minute. M1.received_at is the time the *complete* OHLC was
    actually received, not its market candle timestamp. Trade.confirmed_at is
    when its verified after-fee net result became available. Both must be
    strictly before signal_at. Receipt provenance must be independently audited.
    """
    now = _utc(signal_at, "signal_at")
    if type(received_m1) is not list or len(received_m1) > MAX_INPUT_M1:
        raise ValueError("Received M1 input must be a bounded list")
    if type(confirmed_trades) is not list or len(confirmed_trades) > MAX_CONFIRMED_TRADES:
        raise ValueError("Confirmed trades must be a bounded list")

    m1 = []
    for row in received_m1:
        if type(row) is not dict or row.keys() != M1_FIELDS:
            raise ValueError("Malformed receipt-stamped M1 row")
        opened = _utc(row["open_at"], "M1 open_at")
        received = _utc(row["received_at"], "M1 received_at")
        if received < opened + MINUTE:
            raise ValueError("Completed M1 OHLC receipt precedes candle close")
        if received >= now:
            raise ValueError("M1 OHLC receipt at/after signal is not causal")
        m1.append({key: row[key] for key in ("open_at", "open", "high", "low", "close")})

    trades = []
    for row in confirmed_trades:
        if type(row) is not dict or row.keys() != TRADE_FIELDS:
            raise ValueError("Malformed confirmation-stamped trade row")
        closed = _utc(row["closed_at"], "trade closed_at")
        confirmed = _utc(row["confirmed_at"], "trade confirmed_at")
        if confirmed < closed:
            raise ValueError("Trade result confirmation precedes close")
        if confirmed >= now:
            raise ValueError("Trade result confirmation at/after signal is not causal")
        trades.append({
            "closed_at": row["closed_at"],
            "net_usd_per_oz": row["net_usd_per_oz"],
        })

    return evaluate_gate_from_observed_m1(
        now, m1, trades, lookback=lookback, **frozen_gate_parameters,
    )
