"""Synthetic paired quote/receipt audit; never loads private Gold data."""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_fac025_bidask_receipt import (
    evaluate_gate_from_paired_received_quotes as evaluate,
)

END = datetime(2026, 1, 5, 13, 0, tzinfo=timezone.utc)
SIGNAL = END + timedelta(seconds=1)


def rows():
    start = END - timedelta(minutes=60)
    return [{
        "open_at": start + timedelta(minutes=i),
        "bid_open": 100., "bid_high": 101., "bid_low": 99., "bid_close": 100.,
        "ask_open": 100.2, "ask_high": 101.2, "ask_low": 99.2, "ask_close": 100.2,
        "bid_received_at": start + timedelta(minutes=i + 1),
        "ask_received_at": start + timedelta(minutes=i + 1),
    } for i in range(60)]


def test_complete_synchronized_pair_is_only_research_eligible():
    out = evaluate(SIGNAL, rows(), [])
    assert out["gate"]["status"] == "ELIGIBLE_RESEARCH_ONLY"
    assert out["paired_complete_m1"] == 60
    assert out["quote_side_used_for_context"] == "BID"
    assert out["observed_close_spread_usd_per_oz"]["median"] == pytest.approx(0.2)
    assert out["execution"] == "RESEARCH_ONLY_NO_FILLS_NO_ORDERS"
    assert "NOT_INDEPENDENTLY_AUTHENTICATED" in out["receipt_provenance"]


@pytest.mark.parametrize("field", [
    "ask_open", "ask_high", "ask_low", "ask_close",
])
def test_crossed_ask_side_fails_closed(field):
    data = rows()
    data[5][field] = data[5][field.replace("ask_", "bid_")] - 0.01
    with pytest.raises(ValueError, match="Crossed synchronized"):
        evaluate(SIGNAL, data, [])


@pytest.mark.parametrize("field,value,match", [
    ("ask_high", 98., "Inconsistent ASK"),
    ("bid_low", 102., "Inconsistent BID"),
    ("ask_close", True, "finite positive"),
    ("bid_close", float("nan"), "finite positive"),
    ("ask_open", -1., "finite positive"),
    ("bid_open", "100", "finite positive"),
])
def test_invalid_quote_geometry_and_dtype_fail_closed(field, value, match):
    data = rows()
    data[4][field] = value
    with pytest.raises(ValueError, match=match):
        evaluate(SIGNAL, data, [])


@pytest.mark.parametrize("field", ["bid_received_at", "ask_received_at"])
def test_either_side_late_or_same_instant_blocks(field):
    data = rows()
    data[-1][field] = SIGNAL
    with pytest.raises(ValueError, match="at/after signal"):
        evaluate(SIGNAL, data, [])


@pytest.mark.parametrize("field", ["bid_received_at", "ask_received_at"])
def test_either_side_impossibly_early_blocks(field):
    data = rows()
    data[-1][field] = END - timedelta(microseconds=1)
    with pytest.raises(ValueError, match="precedes M1 close"):
        evaluate(SIGNAL, data, [])


def test_both_quote_receipts_must_be_known_before_signal():
    data = rows()
    data[-1]["ask_received_at"] = END + timedelta(seconds=2)
    assert evaluate(END + timedelta(seconds=3), data, [])["gate"]["status"] == "ELIGIBLE_RESEARCH_ONLY"


def test_missing_minute_never_interpolated():
    data = rows()
    del data[15]
    assert evaluate(SIGNAL, data, [])["gate"]["reason"] == "INCOMPLETE_OBSERVED_M15"


def test_duplicate_minute_never_silently_deduplicated():
    data = rows()
    data.insert(3, data[2].copy())
    with pytest.raises(ValueError, match="strictly increasing"):
        evaluate(SIGNAL, data, [])


def test_trade_loss_halt_is_preserved():
    trade = {"closed_at": END - timedelta(minutes=1),
             "confirmed_at": END - timedelta(minutes=1) + timedelta(seconds=1),
             "net_usd_per_oz": -4.}
    assert evaluate(SIGNAL, rows(), [trade])["gate"]["reason"] == "PREKNOWN_REALIZED_DAILY_LOSS_HALT"


def test_empty_rows_are_not_claimed_eligible():
    out = evaluate(SIGNAL, [], [])
    assert out["gate"]["reason"] == "INSUFFICIENT_OBSERVED_M15"
    assert out["observed_close_spread_usd_per_oz"] is None


def test_schema_extra_field_rejected():
    data = rows()
    data[0]["invented_spread"] = 0.2
    with pytest.raises(ValueError, match="Malformed paired"):
        evaluate(SIGNAL, data, [])


def test_non_utc_receipt_rejected():
    data = rows()
    data[0]["ask_received_at"] = data[0]["ask_received_at"].replace(tzinfo=None)
    with pytest.raises(ValueError, match="UTC-aware"):
        evaluate(SIGNAL, data, [])


def test_bounded_input_rejected():
    from scripts.research_fac025_receipt_gate import MAX_INPUT_M1
    with pytest.raises(ValueError, match="bounded list"):
        evaluate(SIGNAL, [{}] * (MAX_INPUT_M1 + 1), [])
