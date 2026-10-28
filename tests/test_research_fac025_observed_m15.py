"""Synthetic-only FAC025 M1 reconstruction; no Gold source or backtests."""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_fac025_observed_m15 import (
    reconstruct_observed_m15, evaluate_gate_from_observed_m1,
)

UTC = timezone.utc
END = datetime(2026, 1, 5, 13, 0, tzinfo=UTC)
SIGNAL = END + timedelta(seconds=1)


def rows():
    start = END - timedelta(minutes=60)
    return [{"open_at": start + timedelta(minutes=i),
             "open": 100.0, "high": 101.0, "low": 99.0,
             "close": 100.0} for i in range(60)]


def test_reconstructs_four_true_complete_m15_and_passes_causal_gate():
    bars = reconstruct_observed_m15(rows(), SIGNAL)
    assert [bar["end_at"] for bar in bars] == [END - timedelta(minutes=45),
                                                 END - timedelta(minutes=30),
                                                 END - timedelta(minutes=15), END]
    assert [bar["observed_m1_count"] for bar in bars] == [15, 15, 15, 15]
    assert evaluate_gate_from_observed_m1(SIGNAL, rows(), [])["status"] == "ELIGIBLE_RESEARCH_ONLY"


def test_one_missing_minute_is_not_fabricated_and_blocks():
    data = rows()
    del data[22]
    assert [b["observed_m1_count"] for b in reconstruct_observed_m15(data, SIGNAL)] == [15, 14, 15, 15]
    assert evaluate_gate_from_observed_m1(SIGNAL, data, [])["reason"] == "INCOMPLETE_OBSERVED_M15"


def test_wholly_missing_quarter_hour_is_a_market_gap():
    data = [r for r in rows() if not END - timedelta(minutes=45) <= r["open_at"] < END - timedelta(minutes=30)]
    assert evaluate_gate_from_observed_m1(SIGNAL, data, [], lookback=3)["reason"] == "MARKET_GAP_NO_SYNTHETIC_BARS"


def test_missing_latest_quarter_hour_is_stale_not_eligible():
    data = [{**r, "open_at": r["open_at"] - timedelta(minutes=15)} for r in rows()]
    assert evaluate_gate_from_observed_m1(SIGNAL, data, [])["reason"] == "STALE_COMPLETED_M15_CONTEXT"


@pytest.mark.parametrize("mutation,match", [
    (lambda d: d.append(d[-1].copy()), "strictly increasing"),
    (lambda d: d.__setitem__(7, d[6].copy()), "strictly increasing"),
    (lambda d: d.__setitem__(10, {**d[10], "open_at": d[10]["open_at"] + timedelta(seconds=1)}), "exact UTC minute"),
    (lambda d: d.__setitem__(2, {**d[2], "high": 98.0}), "Inconsistent"),
    (lambda d: d.__setitem__(2, {**d[2], "open": True}), "finite positive"),
    (lambda d: d.__setitem__(2, {**d[2], "close": float("nan")}), "finite positive"),
    (lambda d: d.__setitem__(2, {**d[2], "open_at": d[2]["open_at"].replace(tzinfo=None)}), "UTC-aware"),
    (lambda d: d.__setitem__(2, {**d[2], "open_at": d[2]["open_at"].replace(tzinfo=timezone(timedelta(hours=2)))}), "UTC-aware"),
    (lambda d: d.__setitem__(2, {**d[2], "unexpected": 1}), "Malformed"),
])
def test_invalid_m1_fails_closed(mutation, match):
    data = rows()
    mutation(data)
    with pytest.raises(ValueError, match=match):
        reconstruct_observed_m15(data, SIGNAL)


def test_same_instant_m15_and_future_minute_rejected():
    with pytest.raises(ValueError, match="same-instant M15"):
        reconstruct_observed_m15(rows(), END)
    data = rows()
    data.append({**data[-1], "open_at": END})
    with pytest.raises(ValueError, match="M1 close at or after signal"):
        reconstruct_observed_m15(data, SIGNAL)


def test_next_quarter_in_progress_rejected_even_if_last_m1_closed():
    data = rows()
    data.append({**data[-1], "open_at": END})
    with pytest.raises(ValueError, match="Incomplete or same-instant M15"):
        reconstruct_observed_m15(data, END + timedelta(minutes=1, seconds=1))


def test_boundary_is_strict_but_one_microsecond_after_m15_works():
    assert reconstruct_observed_m15(rows(), END + timedelta(microseconds=1))[-1]["end_at"] == END


@pytest.mark.parametrize("bad", [True, 0, 1, 33, 4.0])
def test_invalid_lookback_rejected(bad):
    with pytest.raises(ValueError, match="lookback"):
        reconstruct_observed_m15(rows(), SIGNAL, lookback=bad)


def test_observed_m1_order_and_last_close_used_not_future_revisions():
    data = rows()
    data[-1]["close"] = 100.5
    data[-1]["high"] = 102.0
    bars = reconstruct_observed_m15(data, SIGNAL)
    assert bars[-1]["close"] == 100.5
    assert bars[-1]["high"] == 102.0
    assert bars[-1]["observed_m1_count"] == 15


def test_realized_loss_halt_still_applies_only_to_preknown_closed_trades():
    trade = {"closed_at": END - timedelta(minutes=1), "net_usd_per_oz": -4.0}
    assert evaluate_gate_from_observed_m1(SIGNAL, rows(), [trade])["reason"] == "PREKNOWN_REALIZED_DAILY_LOSS_HALT"


def test_no_rows_never_pass():
    assert evaluate_gate_from_observed_m1(SIGNAL, [], [])["reason"] == "INSUFFICIENT_OBSERVED_M15"
