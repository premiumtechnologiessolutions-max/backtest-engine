"""FAC025 research-only adapter: reconcile canonical fills before daily-loss gating.

A canonical 15-field closed trade must carry one EXTRA independently captured
``confirmed_at`` UTC receipt. This module cannot authenticate that receipt or
prove a broker fill. No orders, raw quotes, P/L predictions or live trading.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

FEE_PER_OUNCE = 0.40
MAX_TRADES = 100_000
FIELDS = frozenset({
    "strategy", "signal_at", "entry_at", "closed_at", "confirmed_at",
    "side", "entry_price", "exit_price", "stop", "target", "ounces",
    "gross_pnl", "cost", "net_pnl", "exit_reason", "gap_minutes",
})
STOP_REASONS = frozenset({"stop", "ambiguous_stop_first", "open_stop", "gap_stop"})
TARGET_REASONS = frozenset({"target", "open_target"})
OTHER_REASONS = frozenset({"time_exit", "end_of_data"})


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC-aware datetime")
    return value.astimezone(timezone.utc)


def _num(value: object, label: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{label} must be finite {'positive ' if positive else ''}numeric, not boolean")
    return float(value)


def _equal(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-7):
        raise ValueError(f"Canonical {label} does not reconcile")


def reconcile_canonical_closed_receipts(trades: list[dict], signal_at: datetime) -> list[dict]:
    """Recompute net USD/oz from every fill and the frozen ALL-IN fee.

    Inputs are chronological canonical 15-field ledgers with an additional
    independently supplied ``confirmed_at``. Output is suitable for the
    existing FAC025 receipt gate, not proof of original-source authenticity.
    """
    now = _utc(signal_at, "signal_at")
    if type(trades) is not list or len(trades) > MAX_TRADES:
        raise ValueError("Canonical closed trades must be a bounded list")
    out: list[dict] = []
    previous_close: datetime | None = None
    for row in trades:
        if type(row) is not dict or row.keys() != FIELDS:
            raise ValueError("Malformed canonical 15-field plus confirmation record")
        signal = _utc(row["signal_at"], "trade signal_at")
        entry = _utc(row["entry_at"], "entry_at")
        closed = _utc(row["closed_at"], "closed_at")
        confirmed = _utc(row["confirmed_at"], "confirmed_at")
        if not signal <= entry <= closed < now:
            raise ValueError("Noncausal canonical signal/entry/close chronology")
        if not closed <= confirmed < now:
            raise ValueError("Confirmation precedes close or is not preknown")
        if previous_close is not None and closed < previous_close:
            raise ValueError("Canonical trades must be ordered by close")
        previous_close = closed
        if type(row["side"]) is not int or row["side"] not in (-1, 1):
            raise ValueError("Canonical side must be integer +1/-1")
        if type(row["gap_minutes"]) is not int or row["gap_minutes"] < 0:
            raise ValueError("Canonical gap_minutes must be nonnegative integer")
        if type(row["strategy"]) is not str or not row["strategy"].strip():
            raise ValueError("Canonical strategy label must be nonempty")
        side = row["side"]
        entry_price = _num(row["entry_price"], "entry_price", positive=True)
        exit_price = _num(row["exit_price"], "exit_price", positive=True)
        stop = _num(row["stop"], "stop", positive=True)
        target = _num(row["target"], "target", positive=True)
        ounces = _num(row["ounces"], "ounces", positive=True)
        if not (stop < entry_price < target if side == 1 else target < entry_price < stop):
            raise ValueError("Canonical stop/target geometry inconsistent with side")
        reason = row["exit_reason"]
        if type(reason) is not str or reason not in STOP_REASONS | TARGET_REASONS | OTHER_REASONS:
            raise ValueError("Unknown canonical exit reason")
        if reason in {"stop", "ambiguous_stop_first"}:
            _equal(exit_price, stop, "stop exit price")
        elif reason in TARGET_REASONS:
            _equal(exit_price, target, "target exit price")
        elif reason in {"open_stop", "gap_stop"} and side * (exit_price - stop) > 1e-7:
            raise ValueError("Canonical adverse open stop improved beyond stop")
        gross = side * (exit_price - entry_price) * ounces
        cost = FEE_PER_OUNCE * ounces
        net = gross - cost
        _equal(_num(row["gross_pnl"], "gross_pnl"), gross, "gross P/L")
        _equal(_num(row["cost"], "cost"), cost, "$0.40/oz roundtrip fee")
        _equal(_num(row["net_pnl"], "net_pnl"), net, "net P/L")
        out.append({"closed_at": closed, "confirmed_at": confirmed,
                    "net_usd_per_oz": net / ounces})
    return out


def evaluate_fac025_with_canonical_receipts(signal_at: datetime, paired_m1: list[dict],
                                             canonical_trades: list[dict], **gate_parameters: object) -> dict:
    """Optional bridge to the paired quote gate; no standalone profit claim."""
    verified = reconcile_canonical_closed_receipts(canonical_trades, signal_at)
    try:
        from scripts.research_fac025_bidask_receipt import evaluate_gate_from_paired_received_quotes
    except ModuleNotFoundError as exc:
        if exc.name != "scripts":
            raise
        from research_fac025_bidask_receipt import evaluate_gate_from_paired_received_quotes
    result = evaluate_gate_from_paired_received_quotes(signal_at, paired_m1, verified, **gate_parameters)
    result["closed_trade_accounting"] = {
        "fee_usd_per_oz_all_in_roundtrip": FEE_PER_OUNCE,
        "trades_recomputed": len(verified),
        "provenance": "RECOMPUTED_NOT_INDEPENDENT_SOURCE_OR_RECEIPT_AUTHENTICATION",
    }
    return result
