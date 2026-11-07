"""Synthetic parity for the actual Limit engine entry-open-beyond-stop exit.

The Limit executor emits this reason when an eligible pending limit is
triggered on a bar opening through its stop. This test verifies that the
research-only FAC025 receipt adapter accepts that canonical adverse fill
without allowing an improved or invented stop fill. No market ZIP is used.
"""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_fac025_canonical_receipts import (
    reconcile_canonical_closed_receipts,
)

NOW = datetime(2026, 1, 5, 13, 0, 1, tzinfo=timezone.utc)


def _receipt(side: int, exit_price: float, ounces: float = 1.0) -> dict:
    entry_at = NOW - timedelta(minutes=2)
    entry_price = 100.0
    stop = 95.0 if side == 1 else 105.0
    target = 110.0 if side == 1 else 90.0
    gross = side * (exit_price - entry_price) * ounces
    cost = 0.40 * ounces
    return {
        "strategy": "synthetic_limit",
        "signal_at": entry_at - timedelta(minutes=1),
        "entry_at": entry_at,
        "closed_at": entry_at,
        "confirmed_at": entry_at + timedelta(seconds=1),
        "side": side,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "stop": stop,
        "target": target,
        "ounces": ounces,
        "gross_pnl": gross,
        "cost": cost,
        "net_pnl": gross - cost,
        "exit_reason": "entry_open_beyond_stop",
        "gap_minutes": 0,
    }


@pytest.mark.parametrize("side,exit_price,expected", [
    (1, 94.0, -6.4),
    (-1, 106.0, -6.4),
    (1, 95.0, -5.4),
    (-1, 105.0, -5.4),
])
def test_actual_limit_engine_adverse_entry_open_reason_is_reconciled(
    side, exit_price, expected,
):
    rows = reconcile_canonical_closed_receipts(
        [_receipt(side, exit_price)], NOW
    )
    assert len(rows) == 1
    assert rows[0]["net_usd_per_oz"] == pytest.approx(expected)


@pytest.mark.parametrize("side,exit_price", [
    (1, 95.01),
    (-1, 104.99),
])
def test_entry_open_reason_rejects_better_than_stop(side, exit_price):
    with pytest.raises(ValueError, match="improved beyond stop"):
        reconcile_canonical_closed_receipts(
            [_receipt(side, exit_price)], NOW
        )


def test_entry_open_reason_still_enforces_exact_per_ounce_fee():
    row = _receipt(1, 94.0, ounces=0.01)
    row["cost"] = 0.0
    row["net_pnl"] = row["gross_pnl"]
    with pytest.raises(ValueError, match="roundtrip fee"):
        reconcile_canonical_closed_receipts([row], NOW)


def test_unknown_entry_open_reason_still_fails_closed():
    row = _receipt(1, 94.0)
    row["exit_reason"] = "entry_open_beyond_target"
    with pytest.raises(ValueError, match="Unknown canonical exit reason"):
        reconcile_canonical_closed_receipts([row], NOW)
