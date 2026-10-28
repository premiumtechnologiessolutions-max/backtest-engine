"""Synthetic-only receipt/confirmation causality checks for FAC025."""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_fac025_receipt_gate import evaluate_gate_from_received_inputs

UTC = timezone.utc
END = datetime(2026, 1, 5, 13, 0, tzinfo=UTC)
SIGNAL = END + timedelta(seconds=1)


def rows():
    start = END - timedelta(minutes=60)
    return [{
        "open_at": start + timedelta(minutes=i),
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
        "received_at": start + timedelta(minutes=i + 1),
    } for i in range(60)]


def trade(*, closed_at=None, confirmed_at=None, net=-4.0):
    closed = closed_at or END - timedelta(minutes=1)
    return {
        "closed_at": closed,
        "net_usd_per_oz": net,
        "confirmed_at": confirmed_at or closed + timedelta(seconds=1),
    }


def run(data=None, trades=None, signal=SIGNAL):
    return evaluate_gate_from_received_inputs(
        signal, rows() if data is None else data,
        [] if trades is None else trades,
    )


def test_all_complete_observations_received_before_signal_are_eligible():
    result = run()
    assert result["status"] == "ELIGIBLE_RESEARCH_ONLY"
    assert result["observed_bars"] == 4
    assert result["execution"] == "RESEARCH_GATE_ONLY_NO_ORDER"


def test_verified_pre_signal_trade_loss_halts_gate():
    assert run(trades=[trade()])["reason"] == "PREKNOWN_REALIZED_DAILY_LOSS_HALT"


@pytest.mark.parametrize("offset,expected", [
    (-1, "precedes candle close"),
    (1, "at/after signal"),
    (2, "at/after signal"),
])
def test_last_m1_receipt_time_must_be_after_close_but_before_signal(offset, expected):
    data = rows()
    data[-1]["received_at"] = END + timedelta(seconds=offset)
    with pytest.raises(ValueError, match=expected):
        run(data)


def test_one_second_late_receipt_is_allowed_only_for_later_signal():
    data = rows()
    data[-1]["received_at"] = END + timedelta(seconds=2)
    with pytest.raises(ValueError, match="at/after signal"):
        run(data)
    assert run(data, signal=END + timedelta(seconds=3))["status"] == "ELIGIBLE_RESEARCH_ONLY"


def test_out_of_order_receipt_times_can_be_causal_when_all_preknown():
    data = rows()
    data[0]["received_at"] = END
    assert run(data)["status"] == "ELIGIBLE_RESEARCH_ONLY"


@pytest.mark.parametrize("field,value,match", [
    ("received_at", END.replace(tzinfo=None), "UTC-aware"),
    ("received_at", END.astimezone(timezone(timedelta(hours=2))), "UTC-aware"),
    ("received_at", "2026-01-05T13:00:00Z", "UTC-aware"),
    ("open_at", True, "UTC-aware"),
])
def test_bad_m1_receipt_schema_fails_closed(field, value, match):
    data = rows()
    data[0][field] = value
    with pytest.raises(ValueError, match=match):
        run(data)


def test_missing_or_extra_m1_receipt_field_fails_closed():
    data = rows()
    del data[0]["received_at"]
    with pytest.raises(ValueError, match="Malformed receipt-stamped"):
        run(data)
    data = rows()
    data[0]["broker_latency_estimate"] = 0
    with pytest.raises(ValueError, match="Malformed receipt-stamped"):
        run(data)


def test_unchanged_observed_m1_validation_still_rejects_bad_ohlc():
    data = rows()
    data[0]["low"] = 102.0
    with pytest.raises(ValueError, match="Inconsistent observed M1"):
        run(data)


@pytest.mark.parametrize("confirmed,match", [
    (END - timedelta(minutes=2), "precedes close"),
    (SIGNAL, "at/after signal"),
    (SIGNAL + timedelta(seconds=1), "at/after signal"),
])
def test_trade_confirmation_must_be_post_close_and_pre_signal(confirmed, match):
    with pytest.raises(ValueError, match=match):
        run(trades=[trade(confirmed_at=confirmed)])


def test_trade_closed_before_signal_but_result_confirmed_after_signal_is_rejected():
    with pytest.raises(ValueError, match="at/after signal"):
        run(trades=[trade(closed_at=END - timedelta(minutes=1), confirmed_at=END + timedelta(seconds=5))])


def test_confirmation_may_be_later_than_close_if_still_pre_signal():
    assert run(trades=[trade(confirmed_at=END)])["reason"] == "PREKNOWN_REALIZED_DAILY_LOSS_HALT"


def test_malformed_trade_receipt_fails_closed():
    t = trade()
    del t["confirmed_at"]
    with pytest.raises(ValueError, match="Malformed confirmation-stamped"):
        run(trades=[t])
    t = trade()
    t["confirmed_at"] = "2026-01-05T12:59:01Z"
    with pytest.raises(ValueError, match="UTC-aware"):
        run(trades=[t])


def test_existing_trade_order_and_nonfinite_validation_still_applies():
    with pytest.raises(ValueError, match="finite numeric"):
        run(trades=[trade(net=float("nan"))])
    first = trade(closed_at=END - timedelta(minutes=1))
    second = trade(closed_at=END - timedelta(minutes=2))
    with pytest.raises(ValueError, match="out-of-order"):
        run(trades=[first, second])


@pytest.mark.parametrize("data,trades", [
    (tuple(), []), ([], tuple()), ([], [None]), ([None], []),
])
def test_input_containers_and_rows_fail_closed(data, trades):
    with pytest.raises(ValueError):
        run(data=data, trades=trades)


def test_bounded_input_preflight():
    from scripts.research_fac025_receipt_gate import (
        MAX_CONFIRMED_TRADES, MAX_INPUT_M1,
    )
    with pytest.raises(ValueError, match="bounded list"):
        run(data=[{}] * (MAX_INPUT_M1 + 1))
    with pytest.raises(ValueError, match="bounded list"):
        run(trades=[{}] * (MAX_CONFIRMED_TRADES + 1))
