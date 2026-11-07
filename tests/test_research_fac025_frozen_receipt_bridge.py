"""Synthetic-only FAC025 frozen grid to receipt-gate integration."""
from datetime import datetime, timedelta, timezone
import copy

import pytest

from scripts.research_fac025_frozen_grid import frozen_specs
from scripts.research_fac025_frozen_receipt_bridge import (
    evaluate_frozen_fac025_receipts as evaluate,
)

UTC = timezone.utc
END = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
DECISION = END + timedelta(seconds=1)


def paired_rows():
    start = END - timedelta(minutes=180)
    return [{
        "open_at": start + timedelta(minutes=i),
        "bid_open": 100.0, "bid_high": 100.1,
        "bid_low": 99.9, "bid_close": 100.0,
        "ask_open": 100.2, "ask_high": 100.3,
        "ask_low": 100.1, "ask_close": 100.2,
        "bid_received_at": start + timedelta(minutes=i + 1),
        "ask_received_at": start + timedelta(minutes=i + 1),
    } for i in range(180)]


def run(spec, rows=None, trades=None):
    return evaluate(
        DECISION, paired_rows() if rows is None else rows,
        [] if trades is None else trades,
        spec_id=spec["id"], parameters=spec["parameters"],
        fingerprint=spec["fingerprint"],
    )


def losing_closed_trade():
    signal = END - timedelta(minutes=3)
    entry = signal + timedelta(minutes=1)
    closed = END - timedelta(seconds=40)
    return {
        "strategy": "synthetic", "signal_at": signal, "entry_at": entry,
        "closed_at": closed, "confirmed_at": closed + timedelta(seconds=1),
        "side": 1, "entry_price": 100.0, "exit_price": 97.5,
        "stop": 97.5, "target": 101.0, "ounces": 1.0,
        "gross_pnl": -2.5, "cost": 0.4, "net_pnl": -2.9,
        "exit_reason": "stop", "gap_minutes": 0,
    }


def test_all_72_frozen_correlated_specs_bind_to_real_causal_gate():
    for spec in frozen_specs():
        result = run(spec)
        assert result["gate"]["status"] == "ELIGIBLE_RESEARCH_ONLY"
        assert result["frozen_spec"]["fingerprint"] == spec["fingerprint"]
        assert result["frozen_spec"]["id"] == spec["id"]
        assert result["frozen_spec"]["shared_capacity_backtest_verified"] is False
        assert result["frozen_spec"]["monthly_net_pnl_usd_per_oz"] == "N/A"


def test_frozen_daily_loss_limits_actually_change_gate_decision():
    specs = frozen_specs()
    tight = next(s for s in specs if s["parameters"]["daily_loss_halt"] == "2")
    loose = next(s for s in specs if s["parameters"]["daily_loss_halt"] == "4")
    assert run(tight, trades=[losing_closed_trade()])["gate"]["reason"] == (
        "PREKNOWN_REALIZED_DAILY_LOSS_HALT"
    )
    assert run(loose, trades=[losing_closed_trade()])["gate"]["status"] == (
        "ELIGIBLE_RESEARCH_ONLY"
    )


@pytest.mark.parametrize("change", ["id", "fingerprint", "parameter", "extra", "bool_id"])
def test_tampered_frozen_identity_or_grid_is_rejected(change):
    spec = copy.deepcopy(frozen_specs()[0])
    if change == "id":
        spec["id"] = frozen_specs()[1]["id"]
    elif change == "fingerprint":
        spec["fingerprint"] = "0" * 64
    elif change == "parameter":
        spec["parameters"]["lookback"] = 16
    elif change == "extra":
        spec["parameters"]["posthoc_months"] = 12
    else:
        spec["id"] = True
    with pytest.raises(ValueError):
        run(spec)


def test_late_ask_receipt_is_never_accepted_as_known_at_decision():
    rows = paired_rows()
    rows[-1]["ask_received_at"] = DECISION
    with pytest.raises(ValueError, match="at/after signal"):
        run(frozen_specs()[0], rows=rows)


def test_crossed_quote_side_is_never_accepted():
    rows = paired_rows()
    rows[-1]["ask_close"] = 99.0
    with pytest.raises(ValueError, match="Crossed|Inconsistent"):
        run(frozen_specs()[0], rows=rows)


def test_missing_m1_blocks_without_interpolation():
    rows = paired_rows()
    del rows[-7]
    assert run(frozen_specs()[0], rows=rows)["gate"]["reason"] == (
        "INCOMPLETE_OBSERVED_M15"
    )


def test_tampered_fee_rejected_before_daily_halt_decision():
    trade = losing_closed_trade()
    trade["cost"] = 0.0
    with pytest.raises(ValueError, match="fee"):
        run(frozen_specs()[0], trades=[trade])
