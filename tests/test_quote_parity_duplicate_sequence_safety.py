"""Direct quote-parity API must not bypass normalized tick sequence safety.

These tests use synthetic quotes only; they do not certify broker ticks.
"""
import numpy as np
import pandas as pd
import pytest

from norisk_quant.quote_parity import compare_bid_ask_ticks_to_m1


def _duplicate_tick_fixture():
    first = pd.Timestamp("2024-01-02T00:00:00Z")
    last = pd.Timestamp("2024-01-02T00:00:50Z")
    ticks = pd.DataFrame(
        {
            "bid": [100.0, 102.0, 101.0],
            "ask": [100.4, 102.5, 101.3],
            "seq": [1, 2, 1],
        },
        index=pd.DatetimeIndex([first, first, last]),
    )
    minutes = pd.DataFrame(
        {
            "o": [100.0], "h": [102.0], "l": [100.0], "c": [101.0],
            "ao": [100.4], "ah": [102.5], "al": [100.4], "ac": [101.3],
        },
        index=pd.DatetimeIndex([first]),
    )
    return ticks, minutes


@pytest.mark.parametrize("unsafe_id", [
    True, False, np.bool_(True), np.bool_(False),
    2**53, -(2**53), str(2**53),
])
def test_direct_quote_parity_rejects_unsafe_duplicate_sequence_ids(unsafe_id):
    ticks, minutes = _duplicate_tick_fixture()
    ticks["seq"] = ticks["seq"].astype(object)
    # Boolean at the first event used to be silently converted to 0/1
    # and could pass both uniqueness and increasing-order checks.
    row = 0 if isinstance(unsafe_id, (bool, np.bool_)) else 1
    ticks.iloc[row, ticks.columns.get_loc("seq")] = unsafe_id
    with pytest.raises(ValueError, match="Invalid duplicate tick timestamp/sequence"):
        compare_bid_ask_ticks_to_m1(ticks, minutes)


def test_direct_quote_parity_accepts_safe_numeric_csv_sequence_strings():
    ticks, minutes = _duplicate_tick_fixture()
    ticks["seq"] = ticks["seq"].astype(str)
    result = compare_bid_ask_ticks_to_m1(ticks, minutes)
    assert bool(result.iloc[0]["both_quotes_match"])


def test_direct_quote_parity_accepts_safe_integer_sequence_ids():
    ticks, minutes = _duplicate_tick_fixture()
    result = compare_bid_ask_ticks_to_m1(ticks, minutes)
    assert bool(result.iloc[0]["both_quotes_match"])
