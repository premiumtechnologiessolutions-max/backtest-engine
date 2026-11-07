"""FAC025 fee and P/L parity must hold per ounce even for tiny positions.

Synthetic-only accounting controls; no private Gold M1 data or backtests.
"""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_fac025_canonical_receipts import (
    reconcile_canonical_closed_receipts,
)

UTC = timezone.utc
NOW = datetime(2026, 1, 5, 13, 0, 1, tzinfo=UTC)


def _trade(ounces: float) -> dict:
    close = NOW - timedelta(seconds=61)
    gross = (96.4 - 100.0) * ounces
    fee = 0.40 * ounces
    return {
        "strategy": "FAC025_SYNTHETIC",
        "signal_at": close - timedelta(minutes=11),
        "entry_at": close - timedelta(minutes=10),
        "closed_at": close,
        "confirmed_at": close + timedelta(seconds=1),
        "side": 1,
        "entry_price": 100.0,
        "exit_price": 96.4,
        "stop": 95.0,
        "target": 110.0,
        "ounces": ounces,
        "gross_pnl": gross,
        "cost": fee,
        "net_pnl": gross - fee,
        "exit_reason": "time_exit",
        "gap_minutes": 0,
    }


@pytest.mark.parametrize("ounces", [1e-9, 0.01, 1.0, 100.0])
def test_correct_fee_and_net_remain_accepted_at_all_sizes(ounces):
    out = reconcile_canonical_closed_receipts([_trade(ounces)], NOW)
    assert len(out) == 1
    assert out[0]["net_usd_per_oz"] == pytest.approx(-4.0)


@pytest.mark.parametrize("field", ["gross_pnl", "cost", "net_pnl"])
def test_tiny_size_cannot_hide_material_per_ounce_corruption(field):
    row = _trade(1e-9)
    # A 0.10 USD/oz distortion is only $1e-10 at this size.
    # It passed the old whole-trade $1e-7 absolute tolerance.
    row[field] += 0.10 * row["ounces"]
    with pytest.raises(ValueError, match="reconcile per ounce"):
        reconcile_canonical_closed_receipts([row], NOW)


def test_tiny_size_cannot_omit_entire_roundtrip_fee():
    row = _trade(1e-9)
    row["cost"] = 0.0
    row["net_pnl"] = row["gross_pnl"]
    with pytest.raises(ValueError, match="roundtrip fee"):
        reconcile_canonical_closed_receipts([row], NOW)


def test_tiny_size_does_not_treat_canceling_fee_errors_as_valid():
    rows = [_trade(1e-9), _trade(1e-9)]
    rows[0]["cost"] = 0.0
    rows[0]["net_pnl"] = rows[0]["gross_pnl"]
    rows[1]["cost"] = 0.8e-9
    rows[1]["net_pnl"] = rows[1]["gross_pnl"] - rows[1]["cost"]
    with pytest.raises(ValueError, match="roundtrip fee"):
        reconcile_canonical_closed_receipts(rows, NOW)
