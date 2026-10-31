"""Synthetic FAC027 execution invariants; never uploads original quotes."""
import pandas as pd
import pytest
from scripts import research_fac027_london_asia as fac


def sample_day(day="2012-05-01", *, entry=True, time_exit=True, gap=False):
    local = pd.Timestamp(day + " 00:00", tz="America/New_York")
    times = list(pd.date_range(local, periods=480, freq="min"))
    if entry:
        times.append(local + pd.Timedelta(hours=8, minutes=1))
    if gap:
        times.append(local + pd.Timedelta(hours=8, minutes=2))
    if time_exit:
        times.append(local + pd.Timedelta(hours=11))
    idx = pd.DatetimeIndex(times).tz_convert("UTC")
    df = pd.DataFrame({"ts": idx.astype("int64") // 10**9,
        "o": [100.] * len(idx), "h": [100.1] * len(idx),
        "l": [99.9] * len(idx), "c": [100.] * len(idx)}, index=idx)
    row = (local.date(), pd.Series(range(len(idx))).to_numpy(),
           100., 90., 10., 95., 102., 0.8, 1.)
    return df, row


def test_stop_first_on_same_observed_minute():
    df, row = sample_day()
    df.iloc[480, df.columns.get_loc("h")] = 102.
    df.iloc[480, df.columns.get_loc("l")] = 98.
    result = fac.execute(row, df, (0.05, 0.3, 0.8, 1.0))
    assert result["reason"] == "stop_first"
    assert result["net"] == pytest.approx(-1.2)


def test_adverse_gap_through_uses_actual_open():
    df, row = sample_day(gap=True)
    df.iloc[481, df.columns.get_loc("o")] = 98.
    result = fac.execute(row, df, (0.05, 0.3, 0.8, 1.0))
    assert result["reason"] == "adverse_gap_stop"
    assert result["net"] == pytest.approx(-2.4)


def test_missing_entry_never_fabricated():
    df, row = sample_day(entry=False)
    assert fac.execute(row, df, (0.05, 0.3, 0.8, 1.0)) is None


def test_missing_future_exit_fails_closed_after_entry_not_preselected():
    df, row = sample_day(time_exit=False)
    with pytest.raises(ValueError, match="missing observed time exit"):
        fac.execute(row, df, (0.05, 0.3, 0.8, 1.0))


def test_dst_monday_entry_uses_new_york_clock():
    df, row = sample_day("2012-03-12")
    result = fac.execute(row, df, (0.05, 0.3, 0.8, 1.0))
    assert result["reason"] == "time"
    assert result["entry_at"].hour == 12
    assert result["exit_at"].hour == 15


def test_grid_exactly_one_family_16_correlated_configs():
    assert len(fac.GRID) == len(set(fac.GRID)) == 16
    assert fac.FEE == 0.40


def test_shared_capacity_priority_does_not_sum_correlated_variants():
    df, row = sample_day()
    solo = fac.simulate(df, fac.GRID[0], days=[row])
    shared = fac.simulate(df, fac.GRID, days=[row])
    assert shared["trades"] == solo["trades"] == 1
    assert shared["net"] == solo["net"] == -0.4
    assert len(shared["monthly"]) == 12
    assert len(shared["monthly_observed_m1_drawdown"]) == 12


def test_time_exit_favorable_gap_is_capped_at_target():
    df, row = sample_day()
    df.iloc[-1, df.columns.get_loc("o")] = 105.
    result = fac.execute(row, df, (0.05, 0.3, 0.8, 1.0))
    assert result["reason"] == "target_at_time_open"
    assert result["net"] == pytest.approx(0.6)
