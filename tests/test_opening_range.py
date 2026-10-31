"""Causal synthetic fixtures for ORB-01 before private historical execution."""
import pandas as pd
import pytest

from norisk_quant.opening_range import OpeningRangeSettings, opening_range_signals


def synthetic_session():
    first = pd.Timestamp("2012-01-09T06:00:00Z")
    rows = []
    for i in range(12):
        hi, lo, close = 2001.0, 1999.0, 2000.0
        if i == 4:
            hi, lo, close = 2001.6, 1999.9, 2001.4
        for minute in range(15):
            rows.append((first + pd.Timedelta(minutes=15*i + minute),
                         2000.0, hi, lo, close))
    return pd.DataFrame(rows, columns=["at", "o", "h", "l", "c"]).set_index("at")


def test_one_causal_signal_after_full_breakout_close():
    src = synthetic_session()
    signals = opening_range_signals(src)
    assert len(signals) == 1
    assert signals[0].side == 1
    assert signals[0].confirmed_at == pd.Timestamp("2012-01-09T07:15:00Z")
    assert signals[0].stop_distance == pytest.approx(2.5)
    assert signals[0].target_distance == pytest.approx(3.75)


def test_incomplete_last_minute_never_confirms():
    src = synthetic_session()
    assert opening_range_signals(src.loc[: "2012-01-09T07:13:00Z"]) == []


def test_missing_opening_or_breakout_minute_invalidates_session():
    src = synthetic_session()
    for at in ("2012-01-09T06:22:00Z", "2012-01-09T07:03:00Z"):
        assert opening_range_signals(src.drop(pd.Timestamp(at))) == []


def test_future_data_cannot_rewrite_old_signal():
    src = synthetic_session()
    prior = opening_range_signals(src)
    modified = src.copy()
    modified.loc[modified.index >= pd.Timestamp("2012-01-09T07:15:00Z"), ["o", "h", "l", "c"]] = [2100, 2200, 1900, 2100]
    assert opening_range_signals(modified) == prior


def test_outside_open_not_a_breakout_signal():
    src = synthetic_session()
    src.loc["2012-01-09T07:00:00Z":"2012-01-09T07:14:00Z", ["o", "h", "l", "c"]] = [2002, 2003, 2001.9, 2002.5]
    assert opening_range_signals(src) == []


@pytest.mark.parametrize("bad", [
    {"start_hour_utc": True}, {"start_hour_utc": 25},
    {"opening_minutes": 45}, {"trade_window_minutes": 60},
    {"reward_risk": float("nan")}, {"max_range_usd": 0.1},
    {"min_stop_usd": 4, "max_stop_usd": 3},
])
def test_bad_frozen_parameters_rejected(bad):
    with pytest.raises(ValueError):
        OpeningRangeSettings(**bad)
