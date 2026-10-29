"""Synthetic fail-closed one-slot CLOSED-ledger audit regressions."""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_fac025_one_slot_audit import audit_one_slot_closed_history

UTC = timezone.utc
NOW = datetime(2026, 1, 5, 13, 0, 1, tzinfo=UTC)
BASE = datetime(2026, 1, 5, 12, 30, tzinfo=UTC)


def trade(minutes=0):
    signal = BASE + timedelta(minutes=minutes)
    entry = signal + timedelta(minutes=1)
    closed = signal + timedelta(minutes=5)
    return {
        "strategy": "FAC025_SYNTHETIC", "signal_at": signal,
        "entry_at": entry, "closed_at": closed,
        "confirmed_at": closed + timedelta(seconds=1),
        "side": 1, "entry_price": 100.0, "exit_price": 96.0,
        "stop": 95.0, "target": 110.0, "ounces": 2.0,
        "gross_pnl": -8.0, "cost": 0.8, "net_pnl": -8.8,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }


def test_empty_history_is_not_misrepresented_as_portfolio_verification():
    out = audit_one_slot_closed_history([], NOW)
    assert out["closed_trades_reconciled"] == 0
    assert out["shared_capacity_backtest_verified"] is False
    assert out["open_position_at_decision"] == "UNKNOWN"
    assert out["monthly_net_pnl_usd_per_oz"] == "N/A"
    assert out["floating_m1_drawdown_usd_per_oz"] == "N/A"


def test_one_and_two_nonoverlapping_closed_trades():
    one = audit_one_slot_closed_history([trade()], NOW)
    assert one["closed_trades_reconciled"] == 1
    out = audit_one_slot_closed_history([trade(), trade(6)], NOW)
    assert out["closed_trades_reconciled"] == 2
    assert out["closed_history_overlap_count"] == 0
    assert out["audit_scope"] == "CLOSED_LEDGER_NONOVERLAP_ONLY"


@pytest.mark.parametrize("second_offset", [2, 3, 4])
def test_overlapping_positions_rejected(second_offset):
    # First position exits at minute 5; second enters at offset+1.
    with pytest.raises(ValueError, match="overlaps"):
        audit_one_slot_closed_history([trade(), trade(second_offset)], NOW)


def test_same_timestamp_exit_and_entry_rejected_without_tick_order():
    # Second entry exactly at first close: 30+5 == 30+4+1.
    with pytest.raises(ValueError, match="same-instant"):
        audit_one_slot_closed_history([trade(), trade(4)], NOW)


def test_canonical_fee_tampering_still_fails_before_capacity_claim():
    altered = trade()
    altered["cost"] = 0.0
    with pytest.raises(ValueError, match="roundtrip fee"):
        audit_one_slot_closed_history([altered], NOW)


def test_future_confirmation_still_fails_before_capacity_claim():
    altered = trade()
    altered["confirmed_at"] = NOW
    with pytest.raises(ValueError, match="not preknown"):
        audit_one_slot_closed_history([altered], NOW)


def test_unordered_close_times_still_fail_canonical_validation():
    with pytest.raises(ValueError, match="ordered by close"):
        audit_one_slot_closed_history([trade(6), trade()], NOW)


def test_nonlist_input_rejected():
    with pytest.raises(ValueError, match="bounded list"):
        audit_one_slot_closed_history((trade(),), NOW)


def test_invalid_exit_geometry_rejected_before_nonoverlap():
    altered = trade()
    altered["stop"] = 101.0
    with pytest.raises(ValueError, match="geometry"):
        audit_one_slot_closed_history([altered], NOW)
