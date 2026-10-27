"""FAC021 frozen M15 CUSUM: causal, gap, DST, gate, same-ID preflight tests."""
import numpy as np
import pandas as pd
import pytest
from scripts import batch_m15_cusum_displacement_grid as fac
from scripts.batch_compression_h1_grid import local_session_masks

def bars(n=80,step=.6):
    idx=pd.date_range('2012-01-02',periods=n,freq='15min',tz='UTC')
    close=100+np.arange(n)*step
    return pd.DataFrame({'o':close-.2,'h':close+.5,'l':close-.5,'c':close,
                         'close_at':idx+pd.Timedelta(minutes=15)},index=idx)

def test_frozen_dimensions_and_prereg():
    assert fac.RULES==36 and fac.TOTAL==2304
    assert fac.SPEC['preregistration_commit']==fac.PREREG
    assert fac.SPEC['roundtrip_all_in_usd_oz']==.4
    assert fac.SPEC['acceptance']['min_fills_each_year']==100

def test_cusum_threshold_reset_and_confirmed_close():
    x=bars()
    t,s,b=fac.cusum_events(x,1.5)
    expected=(x.index[22]+pd.Timedelta(minutes=15)).timestamp()
    assert len(t)>0 and t[0]==int(expected)
    assert np.all(s==1) and np.allclose(b,1.)
    assert t[1]-t[0]==45*60

def test_future_cannot_rewrite_past_events():
    x=bars();past=fac.cusum_events(x.iloc[:60],1.5)
    y=x.copy();y.loc[y.index[60:],'c']-=100
    full=fac.cusum_events(y,1.5)
    for a,b in zip(past,full):assert np.array_equal(a,b[:len(a)])

def test_current_high_low_not_used_in_current_baseline():
    x=bars();original=fac.cusum_events(x.iloc[:23],1.5)
    y=x.iloc[:23].copy();y.loc[y.index[-1],'h']+=1000
    new=fac.cusum_events(y,1.5)
    for a,b in zip(original,new):assert np.array_equal(a,b)

def test_gap_resets_and_requires_twenty_contiguous_bars():
    x=bars();t,_,_=fac.cusum_events(x,1.5)
    y=x.drop(x.index[24]);g,_,_=fac.cusum_events(y,1.5)
    assert all(int((x.index[i]+pd.Timedelta(minutes=15)).timestamp()) not in g for i in range(25,45))
    assert len(t)>len(g)

def test_zero_range_and_nonfinite_do_not_signal():
    x=bars();x['h']=x['c'];x['l']=x['c']
    assert not len(fac.cusum_events(x,1.5)[0])

def test_reject_nonfrozen_thresholds_and_invalid_close_at():
    x=bars()
    with pytest.raises(ValueError):fac.cusum_events(x,2.)
    with pytest.raises(ValueError):fac.cusum_events(x,True)
    y=x.copy();y.loc[y.index[2],'close_at']=y.index[2]
    with pytest.raises(ValueError):fac.cusum_events(y,1.5)

def test_h1_gate_causal_halt_stale_and_preknown():
    t=np.array([3500,7200,10800,14400,18000,21601],np.int64)
    s=np.ones(len(t),np.int8);b=np.ones(len(t))
    ht=np.array([3600,7200,10800,14400],np.int64)
    ratio=np.array([.8,1.5,2.5,.7])
    masks={'ALL':np.ones(len(t),bool)}
    assert fac.h1_gate(t,s,b,ht,ratio,'CALM','ALL',masks)[0].tolist()==[14400,18000]
    assert fac.h1_gate(t,s,b,ht,ratio,'ACTIVE','ALL',masks)[0].tolist()==[7200]

def test_london_and_ny_dst_local_sessions():
    times=pd.DatetimeIndex(['2012-01-10T08:15:00Z','2012-07-10T07:15:00Z',
                            '2012-01-10T14:45:00Z','2012-07-10T13:45:00Z'])
    m=local_session_masks(times.asi8//10**9)
    assert m['LONDON_LOCAL_08_12'].tolist()==[True,True,False,False]
    assert m['NY_LOCAL_0930_1330'].tolist()==[False,False,True,True]

def test_joint_preflight_same_rule_id_not_two_different_winners():
    ids=[f'R{i}' for i in range(fac.RULES)]
    a={k:0 for k in ids};b={k:0 for k in ids}
    a[ids[0]]=120;b[ids[1]]=120
    base={'preregistration_commit':fac.PREREG,'original_zip_sha256':fac.ORIGINAL}
    def rec(y,d):return dict(base,year=y,rule_counts=d)
    assert fac.joint_preflight(rec(2012,a),rec(2013,b))['same_id_rules_ge100_each_year']==0
    b[ids[0]]=100
    assert fac.joint_preflight(rec(2012,a),rec(2013,b))['jointly_eligible_rule_ids']==[ids[0]]
    b[ids[0]]=99.5
    with pytest.raises(ValueError):fac.joint_preflight(rec(2012,a),rec(2013,b))

def test_invalid_h1_chronology_rejected():
    t=np.array([3600,7200],np.int64);s=np.ones(2,np.int8);b=np.ones(2)
    with pytest.raises(ValueError):fac.h1_gate(t,s,b,np.array([7200,3600]),np.ones(2),'CALM','ALL')

def test_preflight_reports_fac021_not_prior_family(tmp_path,monkeypatch):
    empty=(np.empty(0,np.int64),np.empty(0,np.int8),np.empty(0,float))
    monkeypatch.setattr(fac,'signal_streams',lambda m: {f'R{i}':empty for i in range(fac.RULES)})
    monkeypatch.setattr(fac,'fingerprint_loaded_m1',lambda m:'synthetic-test-only')
    result=fac.preflight(None,2012,tmp_path/'fac021.json')
    assert result['id']=='NRF-FAC-021'
    assert result['preregistration_commit']==fac.PREREG
    assert result['no_exit_outcomes_examined'] is True
