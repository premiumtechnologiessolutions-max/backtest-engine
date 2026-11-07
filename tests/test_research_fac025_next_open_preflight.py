"""Synthetic source-M1 chronology tests only; no Gold ZIP or trade results."""
from datetime import datetime, timedelta, timezone
import pytest

from scripts.research_fac025_next_open_preflight import preflight_next_observed_open
from scripts.research_fac025_frozen_entry_policy import POLICY_SHA256

UTC = timezone.utc
SIGNAL = datetime(2026, 1, 5, 14, 15, 1, tzinfo=UTC)


def intent(side="BUY"):
    return {
        "status": "RESEARCH_INTENT_ONLY", "frozen_entry_policy": "FAC025-ENTRY-A",
        "policy_sha256": POLICY_SHA256, "execution": "RESEARCH_INTENT_ONLY_NO_FILLS_NO_ORDERS",
        "max_entry_delay_seconds": 60, "shared_capacity_slots": 1,
        "side": side, "signal_at": SIGNAL.isoformat(),
        "entry_deadline_utc": (SIGNAL + timedelta(seconds=60)).isoformat(),
    }


def row(opened=None):
    opened = opened or datetime(2026, 1, 5, 14, 16, tzinfo=UTC)
    return {"open_at": opened,
            "bid_open": 1000., "bid_high": 1001., "bid_low": 999., "bid_close": 1000.,
            "ask_open": 1000.2, "ask_high": 1001.2, "ask_low": 999.2, "ask_close": 1000.2,
            "bid_received_at": opened + timedelta(minutes=1),
            "ask_received_at": opened + timedelta(minutes=1)}


@pytest.mark.parametrize("side,expected", [("BUY", 1000.2), ("SELL", 1000.)])
def test_first_observed_open_is_candidate_not_fill(side, expected):
    result = preflight_next_observed_open(intent(side), [row()], capacity_free_at_signal=True)
    assert result["status"] == "CANDIDATE_NOT_FILL"
    assert result["candidate_observed_open_usd_per_oz"] == expected
    assert result["entry_delay_seconds"] == 59
    assert result["canonical_execution_verified"] is False
    assert result["entry_fill"] == "N/A"
    assert result["monthly_net_pnl_usd_per_oz"] == "N/A"


def test_missing_capacity_fails_closed_even_with_future_quote():
    assert preflight_next_observed_open(intent(), [row()])["reason"] == "CAPACITY_NOT_CONFIRMED_AT_SIGNAL"
    assert preflight_next_observed_open(intent(), [row()], capacity_free_at_signal=False)["status"] == "BLOCKED"


def test_no_observed_quote_or_gap_beyond_deadline_is_not_fabricated():
    assert preflight_next_observed_open(intent(), [], capacity_free_at_signal=True)["status"] == "BLOCKED"
    later = row(datetime(2026, 1, 5, 14, 17, tzinfo=UTC))
    assert preflight_next_observed_open(intent(), [later], capacity_free_at_signal=True)["reason"] == "NO_OBSERVED_OPEN_WITHIN_FROZEN_60_SECONDS"


def test_exact_signal_instant_open_is_not_eligible():
    same = row(datetime(2026, 1, 5, 14, 15, tzinfo=UTC))
    with pytest.raises(ValueError, match="AFTER decision"):
        preflight_next_observed_open(intent(), [same], capacity_free_at_signal=True)


def test_frozen_deadline_cannot_be_extended():
    changed = intent()
    changed["entry_deadline_utc"] = (SIGNAL + timedelta(seconds=120)).isoformat()
    with pytest.raises(ValueError, match="deadline was modified"):
        preflight_next_observed_open(changed, [row()], capacity_free_at_signal=True)


@pytest.mark.parametrize("change", [
    {"ask_open": 999.}, {"bid_low": 1002.}, {"bid_open": True},
    {"ask_high": float("nan")}, {"bid_received_at": datetime(2026, 1, 5, 14, 16, tzinfo=UTC)},
])
def test_invalid_source_quotes_fail_closed(change):
    bad = row()
    bad.update(change)
    with pytest.raises(ValueError):
        preflight_next_observed_open(intent(), [bad], capacity_free_at_signal=True)


def test_duplicate_or_unordered_observations_fail_closed():
    with pytest.raises(ValueError, match="ordered and unique"):
        preflight_next_observed_open(intent(), [row(), row()], capacity_free_at_signal=True)


def test_bad_intent_and_unverified_policy_rejected():
    changed = intent()
    changed["policy_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="frozen"):
        preflight_next_observed_open(changed, [row()], capacity_free_at_signal=True)
    with pytest.raises(ValueError, match="frozen research intent"):
        preflight_next_observed_open({"status": "FILLED"}, [row()], capacity_free_at_signal=True)


def test_capacity_must_be_boolean_not_truthy():
    with pytest.raises(ValueError, match="boolean"):
        preflight_next_observed_open(intent(), [row()], capacity_free_at_signal=1)
