"""Synthetic source-open consistency regressions, no private Gold ZIP."""
import pandas as pd
import pytest

from norisk_quant.source_exit_integrity import verify_source_open_exit_prices as verify


def source(*, gap=False):
    index = pd.to_datetime([
        "2024-01-02T00:00:00Z", "2024-01-02T00:01:00Z",
        "2024-01-02T00:03:00Z" if gap else "2024-01-02T00:02:00Z",
    ])
    return pd.DataFrame({"o": [100., 99., 94.]}, index=index)


def trade(reason, *, exit_price=94., entry_minute=0, close_minute=2,
          side=1, stop=95., gap=False):
    t = source(gap=gap).index
    return pd.DataFrame([{
        "entry_at": t[entry_minute], "closed_at": t[close_minute],
        "exit_price": exit_price, "exit_reason": reason, "side": side,
        "stop": stop,
    }])


def test_gap_stop_matches_first_bid_open_and_missing_minute():
    assert verify(source(gap=True), trade("gap_stop", gap=True)) == 1


def test_open_stop_matches_contiguous_bid_open():
    assert verify(source(), trade("open_stop")) == 1


def test_entry_open_beyond_stop_same_minute():
    assert verify(source(), trade("entry_open_beyond_stop", entry_minute=2)) == 1


@pytest.mark.parametrize("reason,gap", [("gap_stop", False), ("open_stop", True)])
def test_open_reason_must_match_observed_gap(reason, gap):
    with pytest.raises(AssertionError, match="requires"):
        verify(source(gap=gap), trade(reason, gap=gap))


def test_identically_corrupt_ledgers_cannot_invent_open_price():
    with pytest.raises(AssertionError, match="source M1 BID open"):
        verify(source(), trade("open_stop", exit_price=93.))


def test_entry_open_stop_must_enter_and_close_same_bar():
    with pytest.raises(AssertionError, match="same M1"):
        verify(source(), trade("entry_open_beyond_stop", entry_minute=1))


def test_stop_fill_cannot_be_better_than_protective_stop():
    with pytest.raises(AssertionError, match="improved"):
        verify(source(), trade("open_stop", stop=93.))


def test_exit_timestamp_must_be_present_in_original_source():
    rows = trade("open_stop")
    rows["closed_at"] = pd.Timestamp("2024-01-02T00:04:00Z")
    with pytest.raises(AssertionError, match="missing from source"):
        verify(source(), rows)


def test_no_open_stop_exit_requires_no_price_matching():
    assert verify(source(), trade("target")) == 0


def test_missing_source_open_column_fails_closed():
    with pytest.raises(ValueError, match="numeric BID open"):
        verify(source().drop(columns=["o"]), trade("open_stop"))


def test_short_gap_stop_uses_adverse_source_open():
    assert verify(source(gap=True), trade("gap_stop", gap=True, side=-1, stop=93.)) == 1


def test_duplicate_source_columns_fail_closed():
    m1 = source()
    m1["duplicate"] = m1["o"]
    m1.columns = ["o", "o"]
    with pytest.raises(ValueError, match="duplicate M1 columns"):
        verify(m1, trade("open_stop"))


def test_boolean_exit_price_fails_closed():
    rows = trade("open_stop")
    rows["exit_price"] = True
    with pytest.raises(ValueError, match="finite numeric"):
        verify(source(), rows)


def test_entry_timestamp_must_be_present_in_original_source():
    rows = trade("open_stop")
    rows["entry_at"] = pd.Timestamp("2024-01-02T00:00:30Z")
    with pytest.raises(AssertionError, match="entry timestamp missing from source"):
        verify(source(), rows)


def test_entry_open_beyond_stop_requires_observed_entry_bar():
    rows = trade("entry_open_beyond_stop", entry_minute=2)
    rows["entry_at"] = rows["closed_at"] = pd.Timestamp("2024-01-02T00:04:00Z")
    with pytest.raises(AssertionError, match="entry timestamp missing from source"):
        verify(source(), rows)


def test_duplicate_trade_columns_fail_closed():
    rows = trade("open_stop")
    rows["shadow"] = rows["stop"]
    rows.columns = [*rows.columns[:-1], "stop"]
    with pytest.raises(ValueError, match="unique trade columns"):
        verify(source(), rows)


def test_nonpositive_protective_stop_fails_closed():
    with pytest.raises(ValueError, match="finite positive numeric"):
        verify(source(), trade("open_stop", stop=-1.))
