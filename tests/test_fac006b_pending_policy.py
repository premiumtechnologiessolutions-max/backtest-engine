"""FAC006B opt-in same-strategy pending Market signal execution contract."""
import numpy as np
import pandas as pd
import pytest

from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal
from norisk_quant.portfolio import (
    PortfolioSettings, run_portfolio, validate_portfolio,
)


def minutes():
    idx = pd.date_range("2012-01-02T00:00:00Z", periods=5, freq="min")
    return pd.DataFrame({
        "o": [100.]*5,
        "h": [100.2]*5,
        "l": [99.8,98.8,99.8,99.8,99.8],
        "c": [100.]*5,
    }, index=idx)


def signals(m1):
    return [
        Signal(m1.index[0], 1, 1., 10., "A"),
        Signal(m1.index[1], 1, 2., 2., "A"),
    ]


def settings(*, defer=False):
    return PortfolioSettings(
        ounces_by_strategy={"A":1.},max_open_positions=1,
        max_total_ounces=1.,max_entry_delay_minutes=1,
        all_in_cost_per_ounce=.40,
        defer_same_strategy_market_signals=defer,
    )


def test_default_behavior_stays_immediate_rejection():
    m1=minutes()
    result=run_portfolio(m1,signals(m1),settings())
    assert len(result.trades)==1
    assert result.duplicate_strategy_rejected==1
    assert result.trades.iloc[0].closed_at==m1.index[1]


def test_opt_in_defers_until_next_M1_and_matches_canonical_full_equity():
    m1=minutes()
    result=run_portfolio(m1,signals(m1),settings(defer=True))
    reference=run_fast(m1,signals(m1),Settings(
        ounces=1.,roundtrip_cost_per_ounce=.40,max_entry_delay_minutes=1,
    ))
    assert len(result.trades)==len(reference.trades)==2
    assert result.trades.iloc[1].entry_at==m1.index[2]
    assert result.trades.iloc[1].signal_at==m1.index[1]
    assert result.duplicate_strategy_rejected==0
    np.testing.assert_allclose(result.trades.net_pnl,reference.trades.net_pnl,atol=1e-7)
    np.testing.assert_allclose(result.equity.equity,reference.equity.equity,atol=1e-7)
    assert validate_portfolio(result,settings(defer=True))["status"]=="PASSED"


def test_missing_minute_cannot_create_delayed_fill():
    m1=minutes().drop(minutes().index[2])
    result=run_portfolio(m1,signals(m1),settings(defer=True))
    assert len(result.trades)==1
    assert result.expired_signals==1


def test_other_strategy_capacity_is_not_deferred():
    m1=minutes()
    a=Signal(m1.index[0],1,2.,10.,"A")
    b=Signal(m1.index[1],1,2.,2.,"B")
    cfg=PortfolioSettings(
        ounces_by_strategy={"A":1.,"B":1.},max_open_positions=1,
        max_total_ounces=1.,defer_same_strategy_market_signals=True,
    )
    result=run_portfolio(m1,[a,b],cfg)
    assert len(result.trades)==1
    assert result.capacity_rejected==1


def test_invalid_defer_flag_rejected():
    with pytest.raises(ValueError):
        PortfolioSettings(ounces_by_strategy={"A":1.},
                          defer_same_strategy_market_signals=1)
