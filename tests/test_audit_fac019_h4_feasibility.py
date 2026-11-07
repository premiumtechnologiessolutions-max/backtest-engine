"""Synthetic-only FAC019 H4 feasibility tests; no original market data."""
import numpy as np
import pandas as pd
import pytest
from scripts.audit_fac019_h4_feasibility import h4_capacity, REQUIRED, ORIGINAL_SHA256


def frame(stamps):
    idx = pd.DatetimeIndex(stamps)
    return pd.DataFrame({"close_at": idx + pd.Timedelta(hours=4)}, index=idx)


def test_exactly_eight_and_more_windows():
    idx = pd.date_range("2012-01-03", periods=8, freq="4h", tz="UTC")
    assert h4_capacity(frame(idx))["eligible_eight_bar_windows"] == 1
    idx = pd.date_range("2012-01-03", periods=10, freq="4h", tz="UTC")
    assert h4_capacity(frame(idx))["eligible_eight_bar_windows"] == 3


def test_five_consecutive_is_infeasible():
    idx = pd.date_range("2012-01-03", periods=5, freq="4h", tz="UTC")
    stats = h4_capacity(frame(idx))
    assert stats["max_consecutive_h4_bars"] == 5
    assert stats["eligible_eight_bar_windows"] == 0
    assert stats["can_form_frozen_context"] is False


def test_market_gap_must_not_be_bridged():
    idx = pd.date_range("2012-01-03", periods=10, freq="4h", tz="UTC").delete(5)
    stats = h4_capacity(frame(idx))
    assert stats["max_consecutive_h4_bars"] == 5
    assert stats["eligible_eight_bar_windows"] == 0


def test_two_separate_valid_runs_count_independently():
    a = pd.date_range("2012-01-03", periods=8, freq="4h", tz="UTC")
    b = pd.date_range("2012-01-10", periods=8, freq="4h", tz="UTC")
    assert h4_capacity(frame(a.append(b)))["eligible_eight_bar_windows"] == 2


def test_empty_utc_frame():
    idx = pd.DatetimeIndex([], tz="UTC")
    assert h4_capacity(frame(idx))["max_consecutive_h4_bars"] == 0


@pytest.mark.parametrize("bad", ["naive", "duplicate", "unsorted", "wrong_close", "unaligned"])
def test_malformed_h4_rejected(bad):
    idx = pd.date_range("2012-01-03", periods=8, freq="4h", tz="UTC")
    f = frame(idx)
    if bad == "naive":
        f.index = f.index.tz_localize(None)
    if bad == "duplicate":
        f.index = f.index.where(np.arange(8) != 3, f.index[2])
    if bad == "unsorted":
        f = f.iloc[::-1]
    if bad == "wrong_close":
        f.loc[f.index[2], "close_at"] += pd.Timedelta(minutes=1)
    if bad == "unaligned":
        f.index = f.index + pd.Timedelta(hours=1)
        f["close_at"] = f.index + pd.Timedelta(hours=4)
    with pytest.raises(ValueError):
        h4_capacity(f)


def test_frozen_requirement_and_source_digest():
    assert REQUIRED == 8
    assert ORIGINAL_SHA256 == "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
