"""Synthetic DST and signal timing contract for NY morning hypotheses."""
import pandas as pd
import pytest

from norisk_quant.ny_morning import NewYorkOpenSettings, ny_open_signals


def source(day="2012-01-09", *, rejection=False):
    local_open = pd.Timestamp(f"{day}T08:20:00", tz="America/New_York").tz_convert("UTC")
    rows = []
    for minute in range(55):
        hi, low, close = 100.5, 99.5, 100.0
        if 40 <= minute < 45:
            hi, low, close = (101.2, 99.7, 100.2) if rejection else (101.2, 99.8, 101.0)
        rows.append((local_open + pd.Timedelta(minutes=minute), 100.0, hi, low, close))
    return pd.DataFrame(rows, columns=["at", "o", "h", "l", "c"]).set_index("at")


@pytest.mark.parametrize("date", ["2012-01-09", "2012-07-09"])
def test_new_york_dst_offsets_keep_signal_at_0905_local(date):
    one = ny_open_signals(source(date))
    assert len(one) == 1
    assert one[0].side == 1
    assert one[0].confirmed_at.tz_convert("America/New_York").strftime("%H:%M") == "09:05"
    assert one[0].stop_distance == pytest.approx(1.6)


def test_m5_close_confirmation_not_incomplete_0904():
    data = source()
    assert ny_open_signals(data.iloc[:44]) == []


def test_incomplete_opening_range_is_quarantined():
    data = source().drop(source().index[20])
    assert ny_open_signals(data) == []


def test_rejection_requires_wick_and_close_back_in_range():
    one = ny_open_signals(source(rejection=True), settings=NewYorkOpenSettings(variant="rejection"))
    assert len(one) == 1
    assert one[0].side == -1
    assert one[0].stop_distance == pytest.approx(1.1)


def test_future_bar_modification_cannot_change_existing_signal():
    data = source()
    old = ny_open_signals(data)
    mutated = data.copy()
    mutated.loc[mutated.index >= old[0].confirmed_at, ["o", "h", "l", "c"]] = [100, 110, 90, 100]
    assert ny_open_signals(mutated) == old


@pytest.mark.parametrize("bad", [
    {"variant": "maybe"}, {"penetration_usd": 0},
    {"max_stop_usd": -1}, {"reward_risk": float("nan")},
    {"min_stop_usd": 10, "max_stop_usd": 9},
])
def test_invalid_ny_strategy_parameters_rejected(bad):
    with pytest.raises(ValueError):
        NewYorkOpenSettings(**bad)
