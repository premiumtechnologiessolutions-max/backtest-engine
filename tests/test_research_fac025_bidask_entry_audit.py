"""FAC025 paired quote entry diagnostic: synthetic only, no original Gold ZIP."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from scripts.research_fac025_bidask_entry_audit import audit_bid_reference_entry_quotes
from scripts.research_fac025_canonical_replay import replay_frozen_intents_bid_reference
from scripts.research_fac025_frozen_entry_policy import POLICY_SHA256
from scripts.research_fac025_frozen_grid import frozen_specs

UTC = timezone.utc
AT = datetime(2026, 1, 5, 14, 15, tzinfo=UTC)


def paired(minute, *, spread=.2):
    at = AT + timedelta(minutes=minute)
    return {
        "open_at": at,
        "bid_open": 100., "bid_high": 101., "bid_low": 99., "bid_close": 100.,
        "ask_open": 100. + spread, "ask_high": 101. + spread,
        "ask_low": 99. + spread, "ask_close": 100. + spread,
        "bid_received_at": at + timedelta(minutes=1),
        "ask_received_at": at + timedelta(minutes=1),
    }


def canonical():
    spec = frozen_specs()[0]
    intent = {
        "status": "RESEARCH_INTENT_ONLY", "frozen_entry_policy": "FAC025-ENTRY-A",
        "policy_sha256": POLICY_SHA256,
        "execution": "RESEARCH_INTENT_ONLY_NO_FILLS_NO_ORDERS",
        "max_entry_delay_seconds": 60, "shared_capacity_slots": 1,
        "risk_sizing": "UNDEFINED_NO_POSITION_SIZE",
        "entry_price": "N/A", "stop_price": "N/A", "target_price": "N/A",
        "filter_spec_id": spec["id"], "filter_fingerprint": spec["fingerprint"],
        "side": "BUY", "signal_at": AT.isoformat(),
        "entry_deadline_utc": (AT + timedelta(minutes=1)).isoformat(),
        "risk_distance_usd_per_oz": 1., "target_distance_usd_per_oz": 1.5,
        "fee_usd_per_oz_all_in_roundtrip": .4,
    }
    rows = [paired(i) for i in range(3)]
    minutes = pd.DataFrame(
        [{"o": r["bid_open"], "h": r["bid_high"],
          "l": r["bid_low"], "c": r["bid_close"]} for r in rows],
        index=pd.DatetimeIndex([r["open_at"] for r in rows], tz="UTC"))
    result, _ = replay_frozen_intents_bid_reference(minutes, [intent])
    return rows, result.trades


def test_canonical_reference_is_audited_without_fake_bidask_pnl():
    rows, trades = canonical()
    report = audit_bid_reference_entry_quotes(rows, trades)
    assert report["canonical_reference_trades_audited"] == 1
    assert report["buy_bid_proxy_entries"] == 1
    assert report["buy_entry_ask_minus_bid_max_usd_per_oz"] == pytest.approx(.2)
    assert report["entry_spread_exceeds_fixed_fee_count"] == 0
    assert report["net_pnl_repriced"] is False
    assert report["monthly_pnl"] == "N/A"
    assert report["floating_drawdown"] == "N/A"
    assert report["source_authenticated"] is False


def test_entry_spread_above_all_in_fee_is_flagged_not_double_charged():
    rows, trades = canonical()
    rows[1] = paired(1, spread=.7)
    report = audit_bid_reference_entry_quotes(rows, trades)
    assert report["entry_spread_exceeds_fixed_fee_count"] == 1
    assert report["fixed_roundtrip_all_in_fee_usd_per_oz"] == .4
    assert report["monthly_pnl"] == "N/A"


@pytest.mark.parametrize("field,value", [
    ("ask_open", 99.0),
    ("bid_high", 98.0),
    ("bid_open", True),
    ("ask_close", float("nan")),
    ("bid_received_at", AT + timedelta(minutes=1)),
    ("open_at", AT + timedelta(seconds=1)),
])
def test_malformed_or_unobserved_paired_quote_rejected(field, value):
    rows, trades = canonical()
    rows[1][field] = value
    with pytest.raises(ValueError):
        audit_bid_reference_entry_quotes(rows, trades)


def test_duplicate_and_missing_source_entry_fail_closed():
    rows, trades = canonical()
    with pytest.raises(ValueError, match="strictly increasing"):
        audit_bid_reference_entry_quotes([rows[0], rows[1], rows[1]], trades)
    with pytest.raises(ValueError, match="missing from observed"):
        audit_bid_reference_entry_quotes([rows[0], rows[2]], trades)


@pytest.mark.parametrize("field,value", [
    ("entry_price", 100.2), ("cost", .0), ("side", True),
    ("signal_at", AT + timedelta(minutes=2)),
    ("entry_at", AT + timedelta(minutes=3)),
])
def test_forged_canonical_ledger_fails_closed(field, value):
    rows, trades = canonical()
    trades = trades.copy()
    trades.at[0, field] = value
    with pytest.raises(ValueError):
        audit_bid_reference_entry_quotes(rows, trades)


def test_no_trade_report_is_unavailable_not_zero_profit():
    rows, trades = canonical()
    result = audit_bid_reference_entry_quotes(rows, trades.iloc[0:0])
    assert result["canonical_reference_trades_audited"] == 0
    assert result["observed_entry_spread_median_usd_per_oz"] is None
    assert result["monthly_pnl"] == "N/A"


def test_gaps_counted_without_fabricating_minutes():
    rows, trades = canonical()
    rows.append(paired(8))
    result = audit_bid_reference_entry_quotes(rows, trades)
    assert result["observed_m1_gap_events"] == 1
    assert result["paired_m1_observed"] == 4
