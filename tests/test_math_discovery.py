"""Causal frozen arithmetic research and no-lookahead regression tests."""
import dataclasses
import numpy as np
import pandas as pd
import pytest
from norisk_quant.math_discovery import Formula, arithmetic_signals, formula_scores
from norisk_quant.model import Settings
from norisk_quant.fast_engine import run_fast
from norisk_quant.execution import run


def candles(n=240,seed=17):
    rng=np.random.default_rng(seed)
    o=100+np.cumsum(rng.normal(0,.33,n))
    c=o+rng.normal(0,.27,n)
    h=np.maximum(o,c)+rng.uniform(.02,.4,n)
    l=np.minimum(o,c)-rng.uniform(.02,.4,n)
    return pd.DataFrame({'o':o,'h':h,'l':l,'c':c},
            index=pd.date_range('2024-01-02T09:00:00Z',periods=n,freq='min',tz='UTC'))


def f():return Formula(lookback=10,threshold=.2,cooldown=5)


def test_closed_m1_causality_and_future_append_invariance():
    x=candles()
    a=arithmetic_signals(x.iloc[:150],f())
    b=[s for s in arithmetic_signals(x,f())
       if s.confirmed_at <= x.index[149]+pd.Timedelta(minutes=1)]
    assert a==b
    assert all(s.confirmed_at>=x.index[10]+pd.Timedelta(minutes=1) for s in b)


def test_missing_minute_cannot_reuse_stale_rolling_history():
    data=candles(90)
    deleted=data.drop(data.index[30])
    _,_,valid=formula_scores(deleted,f())
    assert not valid[30:40].any()
    assert valid[41:].any()


def test_reference_fast_same_signals_same_actual_trades_and_fee():
    data=candles()
    signals=arithmetic_signals(data,f())
    assert signals
    s=Settings(ounces=1,roundtrip_cost_per_ounce=.40,max_holding_minutes=240)
    a=run(data,signals,s)
    b=run_fast(data,signals,s)
    for col in ('entry_at','closed_at','side','entry_price','exit_price',
                'net_pnl','cost','exit_reason'):
        pd.testing.assert_series_equal(a.trades[col],b.trades[col],check_names=False)
    assert (a.trades['cost']==.4).all()


@pytest.mark.parametrize('bad',[
    {'lookback':4},{'lookback':True},{'feature_a':6},{'feature_b':-1},
    {'operator_ab':5},{'operator_c':-1},{'reverse':2},
    {'threshold':0},{'threshold':float('nan')},{'threshold':True},
    {'stop_usd':-1},{'reward_risk':float('inf')},{'cooldown':0},
])
def test_strict_formula_grammar_rejects_invalid_inputs(bad):
    with pytest.raises(ValueError):Formula(**bad)


def test_formula_identity_and_expression_are_stable_and_distinct():
    a=Formula();b=dataclasses.replace(a,feature_a=1)
    assert a.identity()==Formula(**dataclasses.asdict(a)).identity()
    assert a.identity()!=b.identity()
    assert 'scaled_return' in a.expression()
    assert len(a.identity())==64


def test_no_eval_or_arbitrary_python_is_admitted():
    with pytest.raises(ValueError):Formula(feature_a='__import__("os").system("touch /tmp/unsafe")')


def test_nan_and_invalid_ohlc_rejected_instead_of_fabricating_signals():
    x=candles(50)
    x.iloc[20,x.columns.get_loc('h')]=float('nan')
    with pytest.raises(ValueError): arithmetic_signals(x,f())
    x=candles(50);x.iloc[20,x.columns.get_loc('l')]=-1
    with pytest.raises(ValueError): arithmetic_signals(x,f())


def test_result_is_deterministic():
    x=candles(750)
    assert arithmetic_signals(x,f())==arithmetic_signals(x.copy(),f())
