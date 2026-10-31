"""Synthetic BID M1 checks; no private market data used."""
import pandas as pd
import pytest
from norisk_quant.source_bar_exit_integrity import verify_source_bar_exit_prices as verify


def market(*, low=98., high=103., final_close=100.):
    ix = pd.date_range("2024-01-02", periods=3, freq="min", tz="UTC")
    return pd.DataFrame({"o": [100., 100., 100.], "h": [101., 101., high],
                         "l": [99.5, 99.5, low], "c": [100., 100., final_close]}, index=ix)


def trade(reason, *, side=1, stop=99., target=102., exit_price=None,
          entry_bar=0, close_bar=2):
    ix = market().index
    if exit_price is None:
        exit_price = stop if reason in {"stop", "ambiguous_stop_first"} else target
    return pd.DataFrame([{"entry_at": ix[entry_bar], "closed_at": ix[close_bar],
                          "entry_price": 100.,
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
    assert verify(market(low=99.5, high=101.), trade("end_of_data", exit_price=100.))["end_of_data"] == 1


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
    assert sum(verify(market(), trade("broker_override")).values()) == 0


def test_short_stop_and_target_ambiguity():
    m = market(low=98., high=103.)
    t = trade("ambiguous_stop_first", side=-1, stop=102., target=99., exit_price=102.)
    assert verify(m, t)["ambiguous_stop_first"] == 1


def test_short_target_only_touch():
    m = market(low=98., high=101.)
    t = trade("target", side=-1, stop=102., target=99., exit_price=99.)
    assert verify(m, t)["target"] == 1


def test_short_open_target_must_be_favorable():
    m = market(low=97., high=101.)
    m.loc[m.index[-1], ["o", "c"]] = [98., 98.]
    t = trade("open_target", side=-1, stop=102., target=99., exit_price=99.)
    assert verify(m, t)["open_target"] == 1


def test_short_open_target_rejects_unfavorable_open():
    t = trade("open_target", side=-1, stop=102., target=99., exit_price=99.)
    with pytest.raises(AssertionError, match="open_target"):
        verify(market(), t)


def test_boolean_source_price_is_rejected():
    m = market()
    m["o"] = True
    with pytest.raises(ValueError):
        verify(m, trade("target"))


@pytest.mark.parametrize("side,stop,target,opening,high,low,reason", [
    (1, 99., 102., 98., 101., 97., "stop"),
    (1, 99., 102., 98., 103., 97., "ambiguous_stop_first"),
    (-1, 102., 99., 103., 104., 100., "stop"),
    (-1, 102., 99., 103., 104., 98., "ambiguous_stop_first"),
])
def test_intrabar_stop_label_cannot_hide_adverse_open(
    side, stop, target, opening, high, low, reason
):
    m = market()
    m.loc[m.index[-1], ["o", "h", "l", "c"]] = [
        opening, high, low, 100.,
    ]
    t = trade(reason, side=side, stop=stop, target=target, exit_price=stop)
    with pytest.raises(AssertionError, match="opening stop priority"):
        verify(m, t)


@pytest.mark.parametrize("side,stop,target,opening,high,low", [
    (1, 99., 102., 103., 104., 100.),
    (-1, 102., 99., 98., 100., 97.),
])
def test_intrabar_target_label_cannot_hide_favorable_open(
    side, stop, target, opening, high, low
):
    m = market()
    m.loc[m.index[-1], ["o", "h", "l", "c"]] = [
        opening, high, low, 100.,
    ]
    t = trade("target", side=side, stop=stop, target=target, exit_price=target)
    with pytest.raises(AssertionError, match="opening target priority"):
        verify(m, t)


@pytest.mark.parametrize("side,stop,target,opening,high,low", [
    (1, 99., 102., 103., 104., 98.),
    (-1, 102., 99., 98., 103., 97.),
])
def test_open_target_wins_even_if_stop_touched_later(
    side, stop, target, opening, high, low
):
    m = market()
    m.loc[m.index[-1], ["o", "h", "l", "c"]] = [
        opening, high, low, 100.,
    ]
    t = trade("open_target", side=side, stop=stop, target=target, exit_price=target)
    assert verify(m, t)["open_target"] == 1


@pytest.mark.parametrize("side,reason,stop,target,exit_price,final_low,final_high,earlier_field,earlier_value", [
    (1, "stop", 99., 102., 99., 98., 101., "l", 98.),
    (1, "target", 99., 102., 102., 99.5, 103., "h", 103.),
    (-1, "stop", 102., 99., 102., 100., 103., "h", 103.),
    (-1, "target", 102., 99., 99., 98., 101., "l", 98.),
])
def test_later_matching_exit_cannot_hide_earlier_trigger(
    side, reason, stop, target, exit_price, final_low, final_high,
    earlier_field, earlier_value
):
    m = market(low=final_low, high=final_high)
    m.loc[m.index[1], earlier_field] = earlier_value
    t = trade(reason, side=side, stop=stop, target=target, exit_price=exit_price)
    with pytest.raises(AssertionError, match="earlier eligible exit"):
        verify(m, t)


def test_entry_bar_stop_cannot_be_ignored_until_later_bar():
    m = market(high=101.)
    m.loc[m.index[0], "l"] = 98.
    with pytest.raises(AssertionError, match="entry-minute stop"):
        verify(m, trade("stop"))


@pytest.mark.parametrize("low,high", [(98., 101.), (99.5, 103.)])
def test_end_of_data_cannot_skip_final_bar_stop_or_target(low, high):
    m = market(low=low, high=high)
    with pytest.raises(AssertionError, match="skipped final-minute exit"):
        verify(m, trade("end_of_data", exit_price=100.))


def test_end_of_data_same_entry_minute_target_may_be_deferred():
    m = market(low=99.5, high=103.)
    t = trade("end_of_data", entry_bar=2, close_bar=2, exit_price=100.)
    assert verify(m, t)["end_of_data"] == 1


def test_entry_bar_target_deferred_then_later_target_is_valid():
    m = market(low=99.5, high=103.)
    m.loc[m.index[0], "h"] = 103.
    assert verify(m, trade("target"))["target"] == 1



def test_limit_entry_provenance_buy_requires_source_low_touch():
    m = market(low=99.5, high=101.)
    t = trade("stop", stop=99., target=102.)
    t.loc[0, "entry_price"] = 99.0 + 0.25
    # First minute low is 99.5, so a BUY limit at 99.25 cannot fill.
    with pytest.raises(AssertionError, match="BUY limit entry was not touched"):
        verify(m, t)


def test_limit_entry_provenance_sell_requires_source_high_touch():
    m = market(low=98., high=103.)
    t = trade("stop", side=-1, stop=104., target=99., exit_price=104.)
    t.loc[0, "entry_price"] = 102.
    # First minute high is 101, so a SELL limit at 102 cannot fill.
    with pytest.raises(AssertionError, match="SELL limit entry was not touched"):
        verify(m, t)


@pytest.mark.parametrize("side,stop,target,entry,match", [
    (1, 100., 102., 100., "BUY requires"),
    (1, 99., 100., 100., "BUY requires"),
    (-1, 100., 99., 100., "SELL requires"),
    (-1, 102., 100., 100., "SELL requires"),
])
def test_limit_entry_must_be_strictly_inside_protective_bounds(
    side, stop, target, entry, match
):
    t = trade("stop", side=side, stop=stop, target=target, exit_price=stop)
    t.loc[0, "entry_price"] = entry
    with pytest.raises(AssertionError, match=match):
        verify(market(), t)


@pytest.mark.parametrize("bad", [True, "100", float("nan"), 0., -1.])
def test_limit_entry_rejects_invalid_price_schema(bad):
    t = trade("stop")
    t["entry_price"] = pd.Series([bad], dtype=object)
    with pytest.raises(ValueError, match="entry_price"):
        verify(market(), t)


def test_limit_entry_price_is_required_for_source_certification():
    t = trade("stop").drop(columns=["entry_price"])
    with pytest.raises(ValueError, match="missing trade fields"):
        verify(market(), t)


def test_limit_entry_provenance_valid_buy_and_sell():
    buy = trade("stop", stop=99., target=102.)
    sell = trade("stop", side=-1, stop=102., target=99., exit_price=102.)
    assert verify(market(high=101.), buy)["stop"] == 1
    assert verify(market(low=99.5, high=103.), sell)["stop"] == 1
