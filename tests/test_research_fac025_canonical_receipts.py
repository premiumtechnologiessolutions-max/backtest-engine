"""FAC025 synthetic canonical fill-to-receipt reconciliation regressions."""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_fac025_canonical_receipts import (
    reconcile_canonical_closed_receipts as reconcile,
    evaluate_fac025_with_canonical_receipts as evaluate,
)

UTC = timezone.utc
END = datetime(2026, 1, 5, 13, 0, tzinfo=UTC)
NOW = END + timedelta(seconds=1)


def trade():
    return {
        "strategy": "FAC025_SYNTHETIC", "signal_at": END - timedelta(minutes=11),
        "entry_at": END - timedelta(minutes=10),
        "closed_at": END - timedelta(minutes=1),
        "confirmed_at": END - timedelta(minutes=1) + timedelta(seconds=1),
        "side": 1, "entry_price": 100., "exit_price": 96.4,
        "stop": 95., "target": 110., "ounces": 2.,
        "gross_pnl": -7.2, "cost": .8, "net_pnl": -8.,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }


def paired():
    start = END - timedelta(minutes=60)
    return [{
        "open_at": start + timedelta(minutes=i),
        "bid_open": 100., "bid_high": 101., "bid_low": 99., "bid_close": 100.,
        "ask_open": 100.2, "ask_high": 101.2, "ask_low": 99.2, "ask_close": 100.2,
        "bid_received_at": start + timedelta(minutes=i + 1),
        "ask_received_at": start + timedelta(minutes=i + 1),
    } for i in range(60)]


def test_exact_fee_normalization_and_loss_halt_bridge():
    result = reconcile([trade()], NOW)
    assert result[0]["net_usd_per_oz"] == pytest.approx(-4.)
    out = evaluate(NOW, paired(), [trade()])
    assert out["gate"]["reason"] == "PREKNOWN_REALIZED_DAILY_LOSS_HALT"
    assert out["closed_trade_accounting"]["trades_recomputed"] == 1
    assert out["closed_trade_accounting"]["fee_usd_per_oz_all_in_roundtrip"] == .4
    assert "NOT_INDEPENDENT" in out["closed_trade_accounting"]["provenance"]


def test_empty_ledger_still_requires_valid_paired_market_context():
    assert reconcile([], NOW) == []
    assert evaluate(NOW, paired(), [])["gate"]["status"] == "ELIGIBLE_RESEARCH_ONLY"


@pytest.mark.parametrize("field,value,match", [
    ("gross_pnl", -7.1, "gross P/L"),
    ("cost", .7, "roundtrip fee"),
    ("net_pnl", -7.9, "net P/L"),
    ("cost", True, "finite"),
    ("side", True, "side"),
    ("side", 0, "side"),
    ("side", 1., "side"),
    ("ounces", 0., "positive"),
    ("entry_price", float("nan"), "finite"),
    ("gap_minutes", -1, "gap_minutes"),
    ("gap_minutes", False, "gap_minutes"),
    ("strategy", "", "strategy"),
    ("exit_reason", "unknown", "exit reason"),
    ("stop", 101., "geometry"),
    ("target", 99., "geometry"),
    ("confirmed_at", NOW, "not preknown"),
    ("confirmed_at", END - timedelta(minutes=2), "precedes close"),
    ("closed_at", NOW, "chronology"),
    ("signal_at", END, "chronology"),
    ("entry_at", END, "chronology"),
])
def test_fail_closed_bad_canonical_ledger(field, value, match):
    row = trade()
    row[field] = value
    with pytest.raises(ValueError, match=match):
        reconcile([row], NOW)


def test_no_undocumented_or_missing_fields():
    row = trade()
    row["fabricated"] = 1
    with pytest.raises(ValueError, match="Malformed"):
        reconcile([row], NOW)
    row = trade()
    del row["confirmed_at"]
    with pytest.raises(ValueError, match="Malformed"):
        reconcile([row], NOW)


def test_unordered_close_is_rejected():
    first = trade()
    second = trade()
    second["signal_at"] -= timedelta(minutes=5)
    second["entry_at"] -= timedelta(minutes=5)
    second["closed_at"] -= timedelta(minutes=5)
    second["confirmed_at"] -= timedelta(minutes=5)
    with pytest.raises(ValueError, match="ordered by close"):
        reconcile([first, second], NOW)


@pytest.mark.parametrize("reason,price,match", [
    ("stop", 96., "stop exit"),
    ("ambiguous_stop_first", 96., "stop exit"),
    ("target", 96., "target exit"),
    ("open_target", 96., "target exit"),
    ("open_stop", 96., "adverse open stop"),
    ("gap_stop", 96., "adverse open stop"),
])
def test_exit_reason_price_geometry_reconciles_independently(reason, price, match):
    row = trade()
    row["exit_reason"] = reason
    row["exit_price"] = price
    row["gross_pnl"] = (price - row["entry_price"]) * row["ounces"]
    row["net_pnl"] = row["gross_pnl"] - row["cost"]
    with pytest.raises(ValueError, match=match):
        reconcile([row], NOW)


def test_valid_stop_and_gap_stop_are_reconciled():
    row = trade()
    row.update(exit_reason="stop", exit_price=95., gross_pnl=-10., net_pnl=-10.8)
    assert reconcile([row], NOW)[0]["net_usd_per_oz"] == pytest.approx(-5.4)
    row.update(exit_reason="gap_stop", exit_price=94., gross_pnl=-12., net_pnl=-12.8)
    assert reconcile([row], NOW)[0]["net_usd_per_oz"] == pytest.approx(-6.4)


def test_non_utc_and_non_datetime_confirmations_rejected():
    row = trade()
    row["confirmed_at"] = row["confirmed_at"].replace(tzinfo=None)
    with pytest.raises(ValueError, match="UTC-aware"):
        reconcile([row], NOW)
    row["confirmed_at"] = "2026-01-05T12:59:01Z"
    with pytest.raises(ValueError, match="UTC-aware"):
        reconcile([row], NOW)


def test_bounded_ledger_and_nonlist_rejected():
    with pytest.raises(ValueError, match="bounded list"):
        reconcile(tuple(), NOW)
    with pytest.raises(ValueError, match="bounded list"):
        reconcile([{}] * 100001, NOW)
