"""FAC015 synthetic causality and frozen-grid regression tests (no raw quotes)."""
import numpy as np
import pandas as pd
import pytest
from scripts.batch_sign_autocorr_fade_grid import (
    TOTAL,SPEC,raw_fade_signals,completed_h1_range_ratio,causal_h1_session_gate,
)

def m15_fixture(signs):
    idx=pd.date_range('2012-01-02',periods=len(signs),freq='15min',tz='UTC')
    op=np.full(len(idx),100.,dtype=float)
    cl=op+np.asarray(signs,dtype=float)
    return pd.DataFrame({'o':op,'h':np.maximum(op,cl)+.5,
                         'l':np.minimum(op,cl)-.5,'c':cl,
                         'close_at':idx+pd.Timedelta(minutes=15)},index=idx)

def test_grid_and_fixed_cost():
    assert TOTAL==SPEC['specs_per_year']==36000
    assert SPEC['roundtrip_all_in_usd_oz']==.4

def test_fade_causal_no_future():
    m=m15_fixture(np.tile([1,-1,1,-1],15))
    t,s,v=raw_fade_signals(m,8,-.4,.5)
    assert len(t)>0 and set(s.tolist())=={-1,1} and np.all(v>0)
    changed=m.copy();changed.loc[changed.index[-1],'c']+=25.
    t2,_,_=raw_fade_signals(changed,8,-.4,.5)
    cutoff=int(m.close_at.iloc[-1].timestamp())
    assert np.array_equal(t[t<cutoff],t2[t2<cutoff])

def test_zero_body_and_missing_m15_rejected():
    m=m15_fixture(np.tile([1,-1],30))
    m.loc[m.index[30],'c']=m.loc[m.index[30],'o']
    t,_,_=raw_fade_signals(m,8,-.4,.5)
    affected=m.close_at.iloc[30:38].astype('int64')//10**9
    assert not np.isin(affected.to_numpy(),t).any()
    m=m15_fixture(np.tile([1,-1],30)).drop(m.index[30])
    t,_,_=raw_fade_signals(m,8,-.4,.5)
    affected=m.close_at.loc[m.index[31:50]].astype('int64')//10**9
    assert not np.isin(affected.to_numpy(),t).any()

def test_constant_sign_variance_fail_closed():
    t,_,_=raw_fade_signals(m15_fixture(np.ones(60)),8,.2,.5)
    assert len(t)==0

def test_h1_gate_stale_future_rejected():
    times=np.array([10000,20000,30000],dtype=np.int64)
    ht=np.array([11000,15000,28000],dtype=np.int64)
    ratio=np.array([.5,.5,2.])
    t,_,_=causal_h1_session_gate(times,np.ones(3,dtype=np.int8),np.ones(3),
                                 ht,ratio,'CALM','ALL',{'ALL':np.ones(3,dtype=bool)})
    assert t.tolist()==[]

def test_h1_range_prior24_and_gap():
    idx=pd.date_range('2012-01-02',periods=30,freq='h',tz='UTC')
    h1=pd.DataFrame({'h':np.full(30,101.),'l':np.full(30,99.),
                     'close_at':idx+pd.Timedelta(hours=1)},index=idx)
    _,ratio=completed_h1_range_ratio(h1)
    assert np.isnan(ratio[:24]).all() and np.allclose(ratio[24:],1.)
    h1.loc[h1.index[-1],'h']=103.
    _,new=completed_h1_range_ratio(h1)
    assert np.allclose(new[24:-1],1.) and new[-1]==2.
    h1.loc[h1.index[-1],'close_at']=h1.close_at.iloc[-2]+pd.Timedelta(days=8)
    _,gapped=completed_h1_range_ratio(h1)
    assert np.isnan(gapped[-1])

@pytest.mark.parametrize('bad',[(7,-.4,.5),(8,-.5,.5),(8,-.4,.7)])
def test_unfrozen_parameters_rejected(bad):
    with pytest.raises(ValueError):
        raw_fade_signals(m15_fixture([1,-1]*30),*bad)
