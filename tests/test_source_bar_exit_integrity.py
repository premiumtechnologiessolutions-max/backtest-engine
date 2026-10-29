"""Synthetic BID M1 checks; no private market data used."""
import pandas as pd
import pytest
from norisk_quant.source_bar_exit_integrity import verify_source_bar_exit_prices as verify


def market(*, low=98., high=103., final_close=100.):
    ix = pd.date_range("2024-01-02", periods=3, freq="min", tz="UTC")
    return pd.DataFrame({"o": [100., 100., 100.], "h": [101., 101., high],
                         "l": [99., 99., low], "c": [100., 100., final_close]}, index=ix)


def trade(reason, *, side=1, stop=99., target=102., exit_price=None,
          entry_bar=0, close_bar=2):
    ix = market().index
    if exit_price is None:
        exit_price = stop if reason in {"stop", "ambiguous_stop_first"} else target
    return pd.DataFrame([{"entry_at": ix[entry_bar], "closed_at": ix[close_bar],
                          "side": side, "stop": stop, "target": target,
                          "exit_price": exit_price, "exit_reason": reason}])


def test_ambiguous_stop_requires_both_extremes():
    assert verify(market(), trade("ambiguous_stop_first"))["ambiguous_stop_first"] == 1


def test_stop_only_valid_without_target_touch():
    assert verify(market(high=101.), trade("stop"))["stop"] == 1


def test_target_only_valid_without_stop_touch():
    assert verify(market(low=99.5), trade("target"))["target"] == 1


def test_open_target_matches_favorable_open():
    m = market(low=100., high=104.)
    m.loc[m.index[-1], ["o", "c"]] = [103., 103.]
    assert verify(m, trade("open_target"))["open_target"] == 1


def test_end_of_data_matches_last_source_close():
    assert verify(market(), trade("end_of_data", exit_price=100.))["end_of_data"] == 1


@pytest.mark.parametrize("reason,kwargs,match", [
    ("stop", {"high": 103.}, "ambiguity"),
    ("ambiguous_stop_first", {"high": 101.}, "ambiguity"),
    ("stop", {"low": 99.5, "high": 101.}, "stop fill"),
    ("target", {"low": 98.}, "target exit"),
])
def test_source_bar_catches_identically_mislabelled_exit(reason, kwargs, match):
    with pytest.raises(AssertionError, match=match):
        verify(market(**kwargs), trade(reason))


def test_target_cannot_exit_on_entry_bar():
    with pytest.raises(AssertionError, match="target exit"):
        verify(market(low=99.5), trade("target", entry_bar=2))


def test_open_target_requires_favorable_source_open():
    with pytest.raises(AssertionError, match="open_target"):
        verify(market(), trade("open_target"))


def test_end_of_data_cannot_invent_last_price():
    with pytest.raises(AssertionError, match="end_of_data"):
        verify(market(), trade("end_of_data", exit_price=101.))


def test_end_of_data_must_be_final_minute():
    with pytest.raises(AssertionError, match="end_of_data"):
        verify(market(), trade("end_of_data", exit_price=100., close_bar=1))


def test_duplicate_trade_columns_fail_closed():
    t = trade("stop")
    t["copy"] = t["stop"]
    t.columns = [*t.columns[:-1], "stop"]
    with pytest.raises(ValueError, match="unique columns"):
        verify(market(), t)


def test_invalid_source_bar_fails_closed():
    m = market()
    m.loc[m.index[-1], "h"] = 99.
    with pytest.raises(ValueError, match="valid OHLC"):
        verify(m, trade("target"))


def test_unknown_exit_reason_not_certified_as_source_checked():
    assert sum(verify(market(), trade("open_stop")).values()) == 0
