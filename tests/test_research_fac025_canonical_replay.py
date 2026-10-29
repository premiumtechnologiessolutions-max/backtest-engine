"""Synthetic only: no original Gold ZIP or performance claim."""
from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
from scripts.research_fac025_canonical_replay import replay_frozen_intents_bid_reference
from scripts.research_fac025_frozen_entry_policy import POLICY_SHA256
from scripts.research_fac025_frozen_grid import frozen_specs

AT = datetime(2026, 1, 5, 14, 15, tzinfo=timezone.utc)


def intent(i=0, side="BUY"):
    s = frozen_specs()[i]
    return {
        "status": "RESEARCH_INTENT_ONLY", "frozen_entry_policy": "FAC025-ENTRY-A",
        "policy_sha256": POLICY_SHA256,
        "execution": "RESEARCH_INTENT_ONLY_NO_FILLS_NO_ORDERS",
        "max_entry_delay_seconds": 60, "shared_capacity_slots": 1,
        "risk_sizing": "UNDEFINED_NO_POSITION_SIZE",
        "entry_price": "N/A", "stop_price": "N/A", "target_price": "N/A",
        "filter_spec_id": s["id"], "filter_fingerprint": s["fingerprint"],
        "side": side, "signal_at": AT.isoformat(),
        "entry_deadline_utc": (AT + timedelta(minutes=1)).isoformat(),
        "risk_distance_usd_per_oz": 1.0, "target_distance_usd_per_oz": 1.5,
        "fee_usd_per_oz_all_in_roundtrip": .4,
    }


def bars(rows):
    return pd.DataFrame([{"o": o, "h": h, "l": l, "c": c}
                         for _, o, h, l, c in rows],
                        index=pd.to_datetime([t for t, *_ in rows], utc=True))


def test_strict_next_open_stop_first_fee_monthly_and_m1_parity():
    m1 = bars([
        ("2026-01-05T14:15:00Z", 100, 100, 100, 100),
        ("2026-01-05T14:16:00Z", 100, 102, 98, 100),
        ("2026-01-05T14:17:00Z", 100, 100, 100, 100),
    ])
    result, s = replay_frozen_intents_bid_reference(m1, [intent()])
    assert len(result.trades) == 1
    t = result.trades.iloc[0]
    assert t["entry_at"] == pd.Timestamp("2026-01-05T14:16:00Z")
    assert t["exit_reason"] == "ambiguous_stop_first"
    assert t["cost"] == pytest.approx(.4)
    assert t["net_pnl"] == pytest.approx(-1.4)
    assert s["worst_month_usd_per_oz"] == pytest.approx(-1.4)
    assert s["max_observed_m1_close_equity_drawdown_usd_per_oz"] == pytest.approx(1.4)
    assert s["reference_fast_parity_m1_marks"] == 3
    assert s["approved_strategies"] == 0


def test_adverse_gap_through_stop_without_fabricated_minutes():
    m1 = bars([
        ("2026-01-05T14:15:00Z", 100, 100, 100, 100),
        ("2026-01-05T14:16:00Z", 100, 100, 100, 100),
        ("2026-01-05T14:20:00Z", 96, 97, 95, 96),
    ])
    result, s = replay_frozen_intents_bid_reference(m1, [intent()])
    assert result.trades.iloc[0]["exit_reason"] == "gap_stop"
    assert result.trades.iloc[0]["exit_price"] == 96
    assert s["worst_month_usd_per_oz"] == pytest.approx(-4.4)


def test_competing_correlated_intents_share_one_slot():
    m1 = bars([
        ("2026-01-05T14:15:00Z", 100, 100, 100, 100),
        ("2026-01-05T14:16:00Z", 100, 100, 100, 100),
        ("2026-01-05T14:17:00Z", 100, 102, 98, 100),
    ])
    result, s = replay_frozen_intents_bid_reference(m1, [intent(1), intent(0)])
    assert len(result.trades) == 1
    assert s["submitted_intents"] == 2
    assert s["independent_hypotheses"] == 1


def test_same_instant_not_filled_and_expired_gap():
    m1 = bars([
        ("2026-01-05T14:15:00Z", 100, 100, 100, 100),
        ("2026-01-05T14:20:00Z", 100, 100, 100, 100),
    ])
    result, s = replay_frozen_intents_bid_reference(m1, [intent()])
    assert result.trades.empty and s["expired_signals"] == 1
    assert s["positive_months"] == 0


@pytest.mark.parametrize("field,value", [
    ("policy_sha256", "0" * 64), ("filter_fingerprint", "0" * 64),
    ("shared_capacity_slots", 2), ("max_entry_delay_seconds", 120),
    ("fee_usd_per_oz_all_in_roundtrip", 0),
    ("risk_distance_usd_per_oz", True), ("target_distance_usd_per_oz", 2),
    ("entry_price", 100), ("status", "FILLED"),
    ("entry_deadline_utc", (AT + timedelta(minutes=2)).isoformat()),
    ("signal_at", AT.replace(tzinfo=None).isoformat()),
])
def test_changed_intent_fails_closed(field, value):
    bad = intent()
    bad[field] = value
    m1 = bars([("2026-01-05T14:16:00Z", 100, 100, 100, 100)])
    with pytest.raises(ValueError):
        replay_frozen_intents_bid_reference(m1, [bad])


def test_duplicate_frozen_intent_rejected():
    m1 = bars([("2026-01-05T14:16:00Z", 100, 100, 100, 100)])
    with pytest.raises(ValueError, match="Duplicate"):
        replay_frozen_intents_bid_reference(m1, [intent(), intent()])
