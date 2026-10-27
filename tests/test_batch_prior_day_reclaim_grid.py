"""Synthetic FAC014 preregistered logic and execution contracts (no private quotes)."""
import numpy as np
import pandas as pd
import pytest
from scripts.batch_prior_day_reclaim_grid import (TOTAL, SPEC, BUFFERS, delayed_reclaims, sessions_masks,
                          gate, replay, prior_utc_day_reference)


def bars(gap=False):
    dates=pd.date_range('2026-01-06T08:00:00Z',periods=25,freq='15min')
    if gap:dates=dates.where(np.arange(25)<22,dates+pd.Timedelta(minutes=15))
    close=np.full(25,100.,dtype=float)
    close[21]=105.;close[22]=100.
    frame=pd.DataFrame({'c':close,'h':np.maximum(close,100.)+.5,'l':np.minimum(close,100.)-.5},index=dates)
    frame['close_at']=frame.index+pd.Timedelta(minutes=15)
    return frame


def test_preregistered_grid_and_reclaim():
    assert TOTAL==27648 and SPEC['roundtrip_all_in_usd_oz']==.4
    m=bars();n=len(m)
    t,s,v=delayed_reclaims(m,np.full(n,20459),np.full(n,103.),np.full(n,97.),
                           np.full(n,2.),np.ones(n,dtype=bool),0.,2)
    assert s.tolist()==[-1]
    assert pd.Timestamp(int(t[0]),unit='s',tz='UTC')==m.close_at.iloc[22]
    assert v.tolist()==[2.]


def test_gap_cancels_pending_reclaim():
    m=bars(gap=True);n=len(m)
    t,s,v=delayed_reclaims(m,np.full(n,20459),np.full(n,103.),np.full(n,97.),
                           np.full(n,2.),np.ones(n,dtype=bool),0.,2)
    assert len(t)==0


def test_closed_h1_only_and_future_not_allowed():
    t=np.array([1000,2000,7000],dtype=np.int64)
    s=np.array([-1,1,1],dtype=np.int8);r=np.ones(3)
    ht=np.array([900,8000],dtype=np.int64)
    trend=np.array([-1,1],dtype=np.int8)
    ratio=np.array([.7,1.2])
    masks={'ALL':np.ones(3,dtype=bool)}
    got=gate(t,s,r,ht,trend,ratio,'FADE','ALIGNED','QUIET','ALL',masks)
    assert got[0].tolist()==[1000]


def test_dst_iana_session():
    dates=np.array([int(pd.Timestamp('2026-01-12T09:00:00Z').timestamp()),
                    int(pd.Timestamp('2026-07-13T08:00:00Z').timestamp())],dtype=np.int64)
    masks=sessions_masks(dates)
    assert masks['LONDON_LOCAL_08_12'].tolist()==[True,True]


def test_gap_through_and_stop_first_and_fee():
    stamps=np.array([60,120,180],dtype=np.int64)
    o=np.array([100.,100.,96.]);h=np.array([100.,102.,97.]);l=np.array([100.,98.,95.]);c=np.array([100.,100.,96.])
    months=np.zeros(3,dtype=np.int8)
    # signal 60 -> enter 60, if both stop and target on same bar: stop-first
    a=replay(stamps,o,h,l,c,months,np.array([60],dtype=np.int64),np.array([1],dtype=np.int8),np.array([1.]),1.,1.)
    assert a[1]==1 and a[2]==-1.4 and abs(a[3]-.4)<1e-12
    # delayed signal enters 120, open gap stop at 180 if it survives 120
    b=replay(stamps,np.array([100.,100.,96.]),np.array([100.,100.5,97.]),np.array([100.,99.5,95.]),c,months,
             np.array([120],dtype=np.int64),np.array([1],dtype=np.int8),np.array([2.]),1.,1.)
    assert b[1]==1 and abs(b[2]-(-4.4))<1e-9