"""FAC020 synthetic-only causal lagged variance-ratio, DST and capacity tests."""
import numpy as np
import pandas as pd
import pytest
from scripts import batch_lagged_variance_ratio_grid as fac
from scripts.batch_compression_h1_grid import local_session_masks

def bars_from_returns(returns,body=.5):
    n=len(returns)
    idx=pd.date_range('2012-01-02',periods=n,freq='15min',tz='UTC')
    close=100.+np.cumsum(np.asarray(returns,dtype=float))
    op=close-body
    hi=np.maximum(op,close)+.1
    lo=np.minimum(op,close)-.1
    return pd.DataFrame({'o':op,'h':hi,'l':lo,'c':close,
                         'close_at':idx+pd.Timedelta(minutes=15)},index=idx)

def test_frozen_grid_and_preregistration():
    assert fac.RULES==192 and fac.TOTAL==fac.SPEC['specs_per_year']==12288
    assert fac.SPEC['roundtrip_all_in_usd_oz']==.4
    assert fac.SPEC['preregistration_commit']==fac.PREREG
    assert fac.SPEC['acceptance']['min_fills_each_year']==100

def test_persist_uses_completed_j_body_and_lagged_vr():
    r=np.tile([.2,.4,.6,.8,1.,1.2,1.4,1.6],12)
    bars=bars_from_returns(r)
    t,s,b=fac.lagged_vr_signals(bars,8,'PERSIST',1.05,.25)
    assert len(t)>0 and (s==1).all() and (b>0).all()
    assert set(t).issubset(set((bars.index+pd.Timedelta(minutes=15)).asi8//10**9))

def test_revert_two_step_ratio_and_fade_direction():
    bars=bars_from_returns(np.tile([1.,-1.],50))
    t,s,b=fac.lagged_vr_signals(bars,8,'REVERT',.85,.25)
    assert len(t)>0 and (s==-1).all() and (b>0).all()

def test_future_mutation_does_not_rewrite_past():
    bars=bars_from_returns(np.tile([.2,.4,.6,.8,1.,1.2,1.4,1.6],12))
    short=fac.lagged_vr_signals(bars.iloc[:70],8,'PERSIST',1.05,.25)
    later=bars.copy();later.iloc[70:,later.columns.get_loc('c')]+=50.
    full=fac.lagged_vr_signals(later,8,'PERSIST',1.05,.25)
    for a,b in zip(short,full):
        assert np.array_equal(a,b[:len(a)])

def test_internal_missing_bar_invalidates_lookback():
    bars=bars_from_returns(np.tile([.2,.4,.6,.8,1.,1.2,1.4,1.6],12))
    t,_,_=fac.lagged_vr_signals(bars,8,'PERSIST',1.05,.25)
    eligible=[int(bars.close_at.iloc[j].timestamp()) for j in range(54,61)
              if int(bars.close_at.iloc[j].timestamp()) in t]
    assert eligible
    gapped=bars.drop(bars.index[50])
    t2,_,_=fac.lagged_vr_signals(gapped,8,'PERSIST',1.05,.25)
    assert all(x not in t2 for x in eligible)

def test_zero_variance_and_zero_body():
    assert not len(fac.lagged_vr_signals(bars_from_returns(np.ones(100)),8,'PERSIST',1.05,.25)[0])
    bars=bars_from_returns(np.tile([.2,.4,.6,.8,1.,1.2,1.4,1.6],12),body=0)
    assert not len(fac.lagged_vr_signals(bars,8,'PERSIST',1.05,.25)[0])

@pytest.mark.parametrize('kw',[
    {'window':9,'state':'PERSIST','threshold':1.05,'body_min':.25},
    {'window':True,'state':'PERSIST','threshold':1.05,'body_min':.25},
    {'window':8,'state':'PERSIST','threshold':.85,'body_min':.25},
    {'window':8,'state':'OTHER','threshold':1.05,'body_min':.25},
    {'window':8,'state':'PERSIST','threshold':1.05,'body_min':.3},
])
def test_reject_nonfrozen_parameters(kw):
    with pytest.raises(ValueError):
        fac.lagged_vr_signals(bars_from_returns(np.ones(50)),**kw)

def test_completed_h1_causal_age_and_halt():
    t=np.array([3500,7200,10800,14400,18000,21601],np.int64)
    s=np.ones(len(t),np.int8);b=np.ones(len(t))
    ht=np.array([3600,7200,10800,14400],np.int64)
    ratio=np.array([.8,1.5,2.5,.7])
    masks={'ALL':np.ones(len(t),dtype=bool)}
    assert fac.h1_session_gate(t,s,b,ht,ratio,'CALM','ALL',masks)[0].tolist()==[14400,18000]
    assert fac.h1_session_gate(t,s,b,ht,ratio,'ACTIVE','ALL',masks)[0].tolist()==[7200]

def test_london_iana_dst_shift():
    t=pd.DatetimeIndex(['2012-01-10T08:15:00Z','2012-07-10T07:15:00Z',
                        '2012-01-10T07:15:00Z','2012-07-10T08:15:00Z'])
    assert local_session_masks(t.asi8//10**9)['LONDON_LOCAL_08_12'].tolist()==[True,True,False,True]

def test_same_id_joint_signal_capacity():
    ids=[f'R{i}' for i in range(fac.RULES)]
    a={k:0 for k in ids};b={k:0 for k in ids}
    a[ids[0]]=110;b[ids[1]]=120
    base={'preregistration_commit':fac.PREREG,'original_zip_sha256':fac.ORIGINAL}
    result=fac.joint_preflight(dict(base,year=2012,rule_counts=a),
                               dict(base,year=2013,rule_counts=b))
    assert result['same_id_rules_ge100_each_year']==0
    assert result['decision']=='STRUCTURALLY_UNREACHABLE_MIN_FILLS'
    b[ids[0]]=100
    assert fac.joint_preflight(dict(base,year=2012,rule_counts=a),
                               dict(base,year=2013,rule_counts=b))['jointly_eligible_rule_ids']==[ids[0]]
    b[ids[0]]=99.5
    with pytest.raises(ValueError):
        fac.joint_preflight(dict(base,year=2012,rule_counts=a),
                            dict(base,year=2013,rule_counts=b))

def test_no_private_data_in_frozen_spec():
    assert 'prices' not in fac.SPEC and 'bid' not in fac.SPEC
    assert fac.SPEC['historically_exposed_not_oos'] is True
