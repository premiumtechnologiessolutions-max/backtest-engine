"""Synthetic-only FAC012B grid, causality, DST, gaps and canonical parity."""
import numpy as np
import pandas as pd
import pytest
from scripts.batch_compression_h1_grid import (
    TOTAL, SPEC, LOOKBACKS, SQUEEZES, MODES, VOL_HALTS, SESSIONS, MULTS,
    compression_breaks, h1_context, causal_gate, local_session_masks,
    replay_normalized, canonical_signals,
)
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings

def test_frozen_spec():
    assert TOTAL==24000
    assert len(LOOKBACKS)*len(SQUEEZES)*len(MODES)*len(VOL_HALTS)*len(SESSIONS)*len(MULTS)**2==TOTAL
    assert SPEC['preregistration_commit']=='bee2e7f072b9a44a2592d007f2dd3fb7d41c23f7'

def _bars():
    idx=pd.date_range('2026-01-05',periods=40,freq='15min',tz='UTC')
    o=np.full(40,100.);h=np.full(40,101.);l=np.full(40,99.);c=np.full(40,100.)
    h[28]=100.1;l[28]=99.9
    h[29]=102.5;l[29]=99.9;c[29]=102.2
    return pd.DataFrame({'o':o,'h':h,'l':l,'c':c,'close_at':idx+pd.Timedelta(minutes=15)},index=idx)

def test_compression_confirmed_only_after_close():
    m=_bars();t,s,v=compression_breaks(m,4,.55)
    assert t.tolist()==[int(m.close_at.iloc[29].timestamp())]
    assert s.tolist()==[1] and v.tolist()==[2.]
    assert len(compression_breaks(m.iloc[:29],4,.55)[0])==0
    with pytest.raises(ValueError):compression_breaks(m,3,.55)

def test_gap_blocks_false_compression():
    m=_bars().drop(_bars().index[20])
    assert len(compression_breaks(m,4,.55)[0])==0

def test_h1_gap_aware_no_fabricated_bars():
    idx=pd.date_range('2026-01-05',periods=40,freq='h',tz='UTC')
    x=np.arange(40)+100.
    h=pd.DataFrame({'o':x,'h':x+2,'l':x-1,'c':x+1,
                    'close_at':idx+pd.Timedelta(hours=1)},index=idx)
    _,tr,rat=h1_context(h)
    assert np.isnan(rat[:25]).all() and np.isfinite(rat[25:]).all()
    g=h.drop(h.index[22])
    _,tr2,rat2=h1_context(g)
    assert np.isfinite(rat2[25:]).all()

def test_dst_local_sessions():
    times=np.array([int(pd.Timestamp(t).timestamp()) for t in
       ('2026-01-15T08:15:00Z','2026-07-15T07:15:00Z',
        '2026-01-15T14:30:00Z','2026-07-15T13:30:00Z')],np.int64)
    masks=local_session_masks(times)
    assert masks['LONDON_LOCAL_08_12'].tolist()==[True,True,False,False]
    assert masks['NY_LOCAL_0930_1330'].tolist()==[False,False,True,True]

def test_asof_h1_no_future_or_stale():
    t=np.array([3600,3660,7200,10800],np.int64)
    s=np.ones(4,np.int8);v=np.ones(4)
    ht=np.array([3700,7200],np.int64)
    assert len(causal_gate(t,s,v,ht,np.ones(2,np.int8),np.array([1.,2.]),'ALIGNED',1.2,'ALL')[0])==0
    ht[0]=3600
    assert causal_gate(t,s,v,ht,np.ones(2,np.int8),np.array([1.,2.]),'ALIGNED',1.2,'ALL')[0].tolist()==[3600,3660]

def test_exact_fee_stop_first_and_canonical_equity():
    idx=pd.date_range('2026-01-05',periods=4,freq='min',tz='UTC')
    m=pd.DataFrame({'o':[100.,100.,100.,100.],'h':[100.5,101.5,100.,100.],
                    'l':[99.5,98.5,100.,100.],'c':[100.,100.,100.,100.]},index=idx)
    stamps=np.asarray(idx.asi8//1_000_000_000,np.int64)
    times=np.array([stamps[0]],np.int64);s=np.array([1],np.int8);v=np.array([1.])
    monthly,n,net,fee,dd,expired=replay_normalized(stamps,m.o.to_numpy(),m.h.to_numpy(),m.l.to_numpy(),m.c.to_numpy(),
         np.zeros(4,np.int8),times,s,v,1.,1.)
    ref=run_fast(m,canonical_signals(times,s,v,1.,1.),Settings(ounces=1.,roundtrip_cost_per_ounce=.4))
    assert n==1 and abs(net+1.4)<1e-8 and abs(fee-.4)<1e-8
    assert abs(ref.trades.net_pnl.sum()-net)<1e-8
    equity=ref.equity.equity
    assert abs((equity.cummax().clip(lower=0)-equity).max()-dd)<1e-8

def test_adverse_gap_through():
    stamps=np.array([0,60,180],np.int64)
    op=np.array([100.,100.,95.]);hi=np.array([100.5,100.5,95.5]);lo=np.array([99.5,99.5,94.5])
    monthly,n,net,fee,dd,expired=replay_normalized(stamps,op,hi,lo,op.copy(),
         np.zeros(3,np.int8),np.array([0],np.int64),np.array([1],np.int8),np.array([1.]),1.,2.)
    assert n==1 and abs(net+5.4)<1e-8 and abs(fee-.4)<1e-8


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_frozen_compression_unit_invariance(unit):
    frame = _bars().copy()
    frame.index = frame.index.as_unit(unit)
    frame["close_at"] = pd.DatetimeIndex(frame["close_at"]).as_unit(unit)
    actual = compression_breaks(frame, 4, .55)
    expected = compression_breaks(_bars(), 4, .55)
    for left, right in zip(actual, expected):
        np.testing.assert_array_equal(left, right)
    assert len(actual[0]) == 1


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_h1_context_unit_invariance(unit):
    idx = pd.date_range("2026-01-05", periods=40, freq="h", tz="UTC")
    x = np.arange(40, dtype=float) + 100
    original = pd.DataFrame({
        "o": x, "h": x + 2, "l": x - 1, "c": x + 1,
        "close_at": idx + pd.Timedelta(hours=1),
    }, index=idx)
    frame = original.copy()
    frame.index = frame.index.as_unit(unit)
    frame["close_at"] = pd.DatetimeIndex(frame["close_at"]).as_unit(unit)
    actual = h1_context(frame)
    expected = h1_context(original)
    for left, right in zip(actual, expected):
        np.testing.assert_array_equal(left, right)
