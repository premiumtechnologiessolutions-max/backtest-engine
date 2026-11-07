"""FAC023 frozen causal M5 path-efficiency regression cases (synthetic only)."""
import numpy as np
import pandas as pd
import pytest
from scripts.batch_m5_semivariance_transition_grid import (
    THRESHOLDS, TOTAL, RULES, semivar_events, h1_gate, joint_preflight,
    canonical_signals, PREREG, ORIGINAL)

def bars(close, start='2026-01-05'):
    idx=pd.date_range(start,periods=len(close),freq='5min',tz='UTC')
    v=np.asarray(close,float)
    return pd.DataFrame({'o':v,'h':v+.1,'l':v-.1,'c':v,
                         'close_at':idx+pd.Timedelta(minutes=5)},index=idx)

def test_frozen_grid():
    assert RULES==36 and TOTAL==2304 and THRESHOLDS==(.25,.40,.55)

def test_completed_only_and_threshold_crossing():
    increments=np.r_[np.tile([-2.,-2.,1.],12),np.ones(25)*3]
    m=bars(200+np.cumsum(increments))
    t,s,b=semivar_events(m,.40)
    assert len(t)>0 and np.any(s==1) and np.all(b>0)
    assert np.all(np.diff(t)>0)

def test_zero_travel_and_bad_threshold():
    assert len(semivar_events(bars(np.ones(45)*100),.25)[0])==0
    with pytest.raises(ValueError):semivar_events(bars(np.arange(45)),.01)

def test_missing_m5_resets_21_bar_history():
    m=bars(100+np.cumsum(np.tile([1.,-2.,3.,-1.],25)))
    m=m.drop(m.index[47])
    t,_,_=semivar_events(m,.25)
    gap=m.index[47].timestamp()
    assert not np.any((t>gap)&(t<gap+21*300))

def test_prior_range_not_current_range():
    m=bars(100+np.arange(50,dtype=float))
    t,_,b=semivar_events(m,.25)
    m.iloc[-1,m.columns.get_loc('h')]+=9999
    tt,_,bb=semivar_events(m,.55)
    assert np.array_equal(t,tt) and np.array_equal(b,bb)

def test_h1_halt_stale_and_above_two():
    t=np.array([3600,7200,10800],np.int64)
    s=np.ones(3,np.int8);b=np.ones(3)
    ht=np.array([3600,7200],np.int64);hr=np.array([.8,2.5])
    masks={'ALL':np.ones(3,dtype=bool)}
    assert h1_gate(t,s,b,ht,hr,'CALM','ALL',masks)[0].tolist()==[3600]
    assert len(h1_gate(t,s,b,ht,hr,'ACTIVE','ALL',masks)[0])==0

def test_joint_preflight_same_id_only():
    a={'year':2012,'preregistration_commit':PREREG,'original_zip_sha256':ORIGINAL,
       'rule_counts':{f'r{i}':100 if i==0 else 0 for i in range(RULES)}}
    b={'year':2013,'preregistration_commit':PREREG,'original_zip_sha256':ORIGINAL,
       'rule_counts':{f'r{i}':100 if i==1 else 0 for i in range(RULES)}}
    assert joint_preflight(a,b)['decision']=='STRUCTURALLY_UNREACHABLE_MIN_FILLS'
    b['rule_counts']['r0']=100
    assert joint_preflight(a,b)['same_id_rules_ge100_each_year']==1

def test_canonical_side_and_distances():
    a=canonical_signals(np.array([1000],np.int64),np.array([-1],np.int8),np.array([2.]),.5,1.5)
    assert len(a)==1 and a[0].side==-1 and a[0].stop_distance==1 and a[0].target_distance==3

def test_cooldown_after_session_gate_per_rule():
    times=np.array([0,300,600,1800,2100],np.int64)
    sides=np.ones(5,np.int8);base=np.ones(5)
    ht=np.array([0,1800],np.int64);hr=np.array([.8,.8])
    masks={'ALL':np.array([False,True,True,True,True])}
    result=h1_gate(times,sides,base,ht,hr,'CALM','ALL',masks)
    assert result[0].tolist()==[300,1800]
