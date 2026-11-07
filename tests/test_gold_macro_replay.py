"""Synthetic integration of real NRFX gold normalization and OpenBB capture."""
import pandas as pd
import pytest

from norisk_quant.data import fingerprint_loaded_m1, validate_loaded_m1
from norisk_quant.gold_macro_replay import (
    gold_m1_closed_events, research_timeline, research_state_at,
)
from norisk_quant.openbb_fred_snapshot import freeze_fred_snapshot

CAPTURE = "2026-11-04T14:00:00Z"


def gold():
    idx = pd.date_range("2026-11-04T13:58:00Z", periods=4, freq="min")
    return pd.DataFrame({
        "o": [2000.0, 2001.0, 2002.0, 2003.0],
        "h": [2001.0, 2002.0, 2003.0, 2004.0],
        "l": [1999.0, 2000.0, 2001.0, 2002.0],
        "c": [2000.5, 2001.5, 2002.5, 2003.5],
        "ao": [2000.2, 2001.2, 2002.2, 2003.2],
        "ah": [2001.2, 2002.2, 2003.2, 2004.2],
        "al": [1999.2, 2000.2, 2001.2, 2002.2],
        "ac": [2000.7, 2001.7, 2002.7, 2003.7],
    }, index=idx)


def macro():
    return freeze_fred_snapshot(
        "GDP", "2024-01-01", "2024-12-31",
        [{"date": "2024-01-01", "GDP": 10.0},
         {"date": "2024-04-01", "GDP": 11.0}], captured_at=CAPTURE)


def test_candle_only_available_after_close():
    frame = gold()
    events = gold_m1_closed_events(
        frame, expected_loaded_fingerprint=fingerprint_loaded_m1(frame))
    assert events[0].event_at_ns == frame.index[0].value
    assert events[0].available_at_ns == frame.index[1].value
    early = research_state_at(frame, expected_loaded_fingerprint=fingerprint_loaded_m1(frame),
                              decision_at="2026-11-04T13:58:30Z")
    assert early["last_gold_bid_close"] is None
    at_close = research_state_at(frame, expected_loaded_fingerprint=fingerprint_loaded_m1(frame),
                                 decision_at="2026-11-04T13:59:00Z")
    assert at_close["last_gold_bid_close"] == 2000.5


def test_macro_is_invisible_before_actual_capture():
    frame = gold()
    fingerprint = fingerprint_loaded_m1(frame)
    old = research_state_at(
        frame, expected_loaded_fingerprint=fingerprint,
        decision_at="2026-11-04T13:59:30Z", fred_snapshot=macro())
    assert old["last_gold_bid_close"] == 2000.5
    assert old["fred_last_observed_value"] is None
    assert old["fred_historical_release_verified"] is False
    new = research_state_at(
        frame, expected_loaded_fingerprint=fingerprint,
        decision_at=CAPTURE, fred_snapshot=macro())
    assert new["fred_last_observed_value"] == 11.0
    assert new["fred_last_observed_period_ns"] == pd.Timestamp("2024-04-01T00:00:00Z").value
    assert new["last_gold_bid_close"] == 2001.5
    assert new["live_trading_authorized"] is False
    assert new["external_research_result_accepted"] is False


def test_merged_order_is_deterministic_and_source_bound():
    frame = gold()
    fingerprint = fingerprint_loaded_m1(frame)
    rows = research_timeline(frame, expected_loaded_fingerprint=fingerprint,
                             fred_snapshot=macro())
    assert len(rows) == 6
    assert [r.available_at_ns for r in rows] == sorted(r.available_at_ns for r in rows)
    assert [r.source for r in rows] == [
        "gold", "gold", "openbb_fred", "openbb_fred", "gold", "gold"]
    assert len(set(r.source_sha256 for r in rows)) == 2


def test_mutated_market_quotes_fail_closed():
    frame = gold()
    fingerprint = fingerprint_loaded_m1(frame)
    frame.loc[frame.index[0], "c"] += 0.1
    with pytest.raises(ValueError, match="source differs"):
        gold_m1_closed_events(frame, expected_loaded_fingerprint=fingerprint)


def test_crossed_prices_missing_and_nonfinite_rejected():
    for key, value in [("ac", 1999.0), ("h", float("nan"))]:
        frame = gold()
        frame.loc[frame.index[0], key] = value
        with pytest.raises(ValueError):
            gold_m1_closed_events(
                frame, expected_loaded_fingerprint="a" * 64)


def test_gaps_are_not_synthesized():
    frame = gold().drop(gold().index[1])
    assert len(gold_m1_closed_events(
        frame, expected_loaded_fingerprint=fingerprint_loaded_m1(frame))) == 3


def test_unknown_or_wrong_fingerprint_rejected():
    frame = gold()
    for bad in ("x", "a" * 64):
        with pytest.raises(ValueError):
            gold_m1_closed_events(frame, expected_loaded_fingerprint=bad)


def test_decision_time_must_be_tz_aware():
    frame = gold()
    with pytest.raises(ValueError, match="timezone-aware"):
        research_state_at(frame, expected_loaded_fingerprint=fingerprint_loaded_m1(frame),
                          decision_at="2026-11-04T13:59:00")


def test_replay_window_limit():
    frame = gold()
    assert validate_loaded_m1(frame) is frame
    too_long = pd.concat([frame] * 12501, ignore_index=True)
    with pytest.raises(ValueError, match="50000"):
        gold_m1_closed_events(too_long, expected_loaded_fingerprint="a" * 64)
