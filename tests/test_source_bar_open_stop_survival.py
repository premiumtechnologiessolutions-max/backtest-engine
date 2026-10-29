"""Synthetic open-stop survival regressions; no proprietary XAUUSD data."""
import pandas as pd
import pytest

from norisk_quant.source_bar_exit_integrity import verify_source_bar_exit_prices


def bars(*, gap=False, short=False):
    index = pd.to_datetime([
        "2024-01-02T00:00:00Z",
        "2024-01-02T00:01:00Z",
        "2024-01-02T00:03:00Z" if gap else "2024-01-02T00:02:00Z",
    ])
    if short:
        last = (103., 104., 100., 103.)
    else:
        last = (94., 100., 93., 95.)
    return pd.DataFrame({
        "o": [100., 100., last[0]],
        "h": [101., 101., last[1]],
        "l": [99.5, 99.5, last[2]],
        "c": [100., 100., last[3]],
    }, index=index)


def row(m1, reason, *, short=False, entry_bar=0, exit_price=None):
    stop, target = (102., 99.) if short else (95., 102.)
    return pd.DataFrame([{
        "entry_at": m1.index[entry_bar],
        "closed_at": m1.index[-1],
        "side": -1 if short else 1,
        "stop": stop,
        "target": target,
        "exit_price": float(m1["o"].iloc[-1]) if exit_price is None else exit_price,
        "exit_reason": reason,
    }])


@pytest.mark.parametrize("reason,gap,short,entry_bar", [
    ("open_stop", False, False, 0),
    ("gap_stop", True, False, 0),
    ("entry_open_beyond_stop", False, False, 2),
    ("open_stop", False, True, 0),
    ("gap_stop", True, True, 0),
    ("entry_open_beyond_stop", False, True, 2),
])
def test_valid_source_open_stop_is_audited(reason, gap, short, entry_bar):
    m1 = bars(gap=gap, short=short)
    result = verify_source_bar_exit_prices(
        m1, row(m1, reason, short=short, entry_bar=entry_bar)
    )
    assert result[reason] == 1


@pytest.mark.parametrize("short,field,value", [
    (False, "l", 94.),
    (False, "h", 103.),
    (True, "h", 103.),
    (True, "l", 98.),
])
def test_open_stop_cannot_hide_earlier_stop_or_target(short, field, value):
    m1 = bars(short=short)
    m1.loc[m1.index[1], field] = value
    with pytest.raises(AssertionError, match="earlier eligible exit"):
        verify_source_bar_exit_prices(m1, row(m1, "open_stop", short=short))


def test_open_stop_cannot_hide_entry_minute_stop():
    m1 = bars()
    m1.loc[m1.index[0], "l"] = 94.
    with pytest.raises(AssertionError, match="entry-minute stop"):
        verify_source_bar_exit_prices(m1, row(m1, "open_stop"))


@pytest.mark.parametrize("reason,gap", [
    ("gap_stop", False),
    ("open_stop", True),
])
def test_open_stop_gap_label_must_match_observed_minute_spacing(reason, gap):
    m1 = bars(gap=gap)
    with pytest.raises(AssertionError, match="requires"):
        verify_source_bar_exit_prices(m1, row(m1, reason))


def test_open_stop_must_match_source_open():
    m1 = bars()
    with pytest.raises(AssertionError, match="observed BID open"):
        verify_source_bar_exit_prices(m1, row(m1, "open_stop", exit_price=93.))


def test_open_stop_cannot_be_favorable_to_stop():
    m1 = bars()
    m1.loc[m1.index[-1], ["o", "h", "l", "c"]] = [96., 100., 95.5, 96.]
    with pytest.raises(AssertionError, match="favorable to protective stop"):
        verify_source_bar_exit_prices(m1, row(m1, "open_stop"))


def test_entry_open_stop_requires_same_entry_minute():
    m1 = bars()
    with pytest.raises(AssertionError, match="entry minute"):
        verify_source_bar_exit_prices(m1, row(m1, "entry_open_beyond_stop"))
