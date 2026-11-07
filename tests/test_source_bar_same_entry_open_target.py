"""Opening-target precedence must respect the LIMIT entry time.

Synthetic BID candles only; no proprietary gold archive or forward sample.
"""
import pandas as pd
import pytest

from norisk_quant.limit_engine import LimitOrder, run_limits
from norisk_quant.model import Settings
from norisk_quant.source_bar_exit_integrity import verify_source_bar_exit_prices


@pytest.mark.parametrize(
    "side,opening,high,low,stop,target",
    [
        (1, 103.0, 104.0, 98.0, 99.0, 102.0),
        (-1, 97.0, 103.0, 96.0, 102.0, 99.0),
    ],
)
def test_favorable_open_before_same_bar_limit_entry_cannot_override_stop_first(
    side, opening, high, low, stop, target
):
    # The favorable opening target print occurs BEFORE the LIMIT entry.
    # The bar then spans both the entry and protective stop. The executor
    # conservatively records ambiguous_stop_first, not open_target.
    at = pd.Timestamp("2024-01-02T00:00:00Z")
    m1 = pd.DataFrame(
        {"o": [opening], "h": [high], "l": [low], "c": [100.0]},
        index=pd.DatetimeIndex([at]),
    )
    order = LimitOrder(
        placed_at=at, expires_at=at, side=side, price=100.0,
        stop=stop, target=target,
    )
    result = run_limits(
        m1, [order],
        Settings(ounces=1.0, roundtrip_cost_per_ounce=0.40),
    )
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["entry_at"] == at
    assert trade["closed_at"] == at
    assert trade["exit_reason"] == "ambiguous_stop_first"
    assert trade["exit_price"] == stop
    assert trade["cost"] == pytest.approx(0.40)
    assert verify_source_bar_exit_prices(m1, result.trades)["ambiguous_stop_first"] == 1


@pytest.mark.parametrize(
    "side,opening,high,low,stop,target",
    [
        (1, 103.0, 104.0, 98.0, 99.0, 102.0),
        (-1, 97.0, 103.0, 96.0, 102.0, 99.0),
    ],
)
def test_favorable_open_still_overrides_intrabar_label_for_older_position(
    side, opening, high, low, stop, target
):
    # Identical second-bar geometry, but the position was ALREADY open.
    # The favorable open must trigger open_target; a fabricated stop-first
    # intrabar label must fail source verification.
    index = pd.date_range("2024-01-02", periods=2, freq="min", tz="UTC")
    m1 = pd.DataFrame(
        {
            "o": [100.0, opening],
            "h": [101.0, high],
            "l": [99.5, low],
            "c": [100.0, 100.0],
        },
        index=index,
    )
    fabricated = pd.DataFrame([{
        "entry_at": index[0], "closed_at": index[1],
        "entry_price": 100.0, "exit_price": stop,
        "side": side, "stop": stop, "target": target,
        "exit_reason": "ambiguous_stop_first",
    }])
    with pytest.raises(AssertionError, match="opening target priority"):
        verify_source_bar_exit_prices(m1, fabricated)
