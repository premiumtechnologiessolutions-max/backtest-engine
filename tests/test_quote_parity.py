import pandas as pd
import pytest
from norisk_quant.quote_parity import compare_bid_ask_ticks_to_m1, summarize_bid_ask_parity


def fixture():
    times = pd.to_datetime(["2024-01-02T00:00:00Z", "2024-01-02T00:00:20Z", "2024-01-02T00:00:50Z"], utc=True)
    ticks = pd.DataFrame({"bid": [100., 102., 101.], "ask": [100.4, 102.5, 101.3]}, index=times)
    bars = pd.DataFrame({"o": [100.], "h": [102.], "l": [100.], "c": [101.],
                         "ao": [100.4], "ah": [102.5], "al": [100.4], "ac": [101.3]},
                        index=pd.to_datetime(["2024-01-02T00:00:00Z"], utc=True))
    return ticks, bars


def test_both_quote_sides_match_and_summary():
    ticks, bars = fixture()
    report = compare_bid_ask_ticks_to_m1(ticks, bars)
    assert report.iloc[0]["both_quotes_match"]
    assert summarize_bid_ask_parity(report)["status"] == "PASSED_OBSERVED_OHLC_ONLY"


def test_ask_mismatch_not_hidden_by_matching_bid():
    ticks, bars = fixture()
    bars["ah"] += .1
    report = compare_bid_ask_ticks_to_m1(ticks, bars)
    assert report.iloc[0]["ask_mismatch"]
    assert not report.iloc[0]["bid_mismatch"]
    assert summarize_bid_ask_parity(report)["status"] == "FAILED_OR_INCOMPLETE"


def test_missing_minute_is_not_a_false_match():
    ticks, bars = fixture()
    future = bars.copy()
    future.index = future.index + pd.Timedelta(minutes=1)
    report = compare_bid_ask_ticks_to_m1(ticks, pd.concat([bars, future]))
    assert report.iloc[1]["status"] == "NO_TICKS"
    assert not report.iloc[1]["both_quotes_match"]
    assert summarize_bid_ask_parity(report)["missing_tick_minutes"] == 1


@pytest.mark.parametrize("mutation", ["crossed_tick", "nan_ask", "crossed_m1", "nan_tolerance", "duplicate_m1", "unsorted_tick"])
def test_corrupt_quotes_and_timestamps_fail_closed(mutation):
    ticks, bars = fixture()
    if mutation == "crossed_tick": ticks.loc[ticks.index[0], "ask"] = 99
    elif mutation == "nan_ask": ticks.loc[ticks.index[0], "ask"] = float("nan")
    elif mutation == "crossed_m1": bars["al"] = 99
    elif mutation == "duplicate_m1": bars = pd.concat([bars, bars])
    elif mutation == "unsorted_tick": ticks = ticks.iloc[::-1]
    elif mutation == "nan_tolerance":
        with pytest.raises(ValueError): compare_bid_ask_ticks_to_m1(ticks, bars, tolerance=float("nan"))
        return
    with pytest.raises(ValueError): compare_bid_ask_ticks_to_m1(ticks, bars)


def test_duplicate_tick_timestamp_requires_source_sequence():
    ticks, bars = fixture()
    ticks.index = pd.DatetimeIndex([ticks.index[0], ticks.index[0], ticks.index[-1]])
    with pytest.raises(ValueError, match="sequence"):
        compare_bid_ask_ticks_to_m1(ticks, bars)
    ticks["seq"] = [0, 1, 0]
    report = compare_bid_ask_ticks_to_m1(ticks, bars)
    assert report.iloc[0]["both_quotes_match"]


def test_no_overlap_explicitly_incomplete():
    ticks, bars = fixture()
    bars.index += pd.Timedelta(days=1)
    report = compare_bid_ask_ticks_to_m1(ticks, bars)
    assert summarize_bid_ask_parity(report)["status"] == "FAILED_OR_INCOMPLETE"
    assert summarize_bid_ask_parity(report)["coverage_fraction"] == 0


def test_duplicate_tick_string_sequences_use_numeric_not_lexical_order():
    ticks, bars = fixture()
    ticks.index = pd.DatetimeIndex([ticks.index[0]] * 3)
    ticks["seq"] = ["1", "10", "2"]
    with pytest.raises(ValueError, match="already be sorted"):
        compare_bid_ask_ticks_to_m1(ticks, bars)


@pytest.mark.parametrize("source,column", [
    ("tick", "bid"), ("tick", "ask"),
    ("M1", "o"), ("M1", "h"), ("M1", "l"), ("M1", "c"),
    ("M1", "ao"), ("M1", "ah"), ("M1", "al"), ("M1", "ac"),
])
@pytest.mark.parametrize("bad_type", ["boolean", "numeric_text"])
def test_parity_rejects_boolean_or_text_quote_dtype(source, column, bad_type):
    """Do not certify malformed quotes by silently coercing them to float."""
    ticks, bars = fixture()
    frame = ticks if source == "tick" else bars
    if bad_type == "boolean":
        frame[column] = True
    else:
        frame[column] = frame[column].astype(str)
    with pytest.raises(ValueError, match="numeric non-boolean BID/ASK"):
        compare_bid_ask_ticks_to_m1(ticks, bars)


def test_parity_still_accepts_valid_integer_and_float_quote_dtypes():
    ticks, bars = fixture()
    ticks["bid"] = ticks["bid"].astype(int)
    bars["o"] = bars["o"].astype(int)
    report = compare_bid_ask_ticks_to_m1(ticks, bars)
    assert bool(report.iloc[0]["both_quotes_match"])
