"""FAC013 frozen causal sweep and no-fabrication contract tests."""
import numpy as np
import pandas as pd
import pytest
from scripts.batch_liquidity_sweep_h1_grid import (TOTAL, LOOKBACKS, SPEC,
    sweep_rejections, gate, canonical_signals)
from norisk_quant.model import Signal


def _bars(gap=False):
    stamps=pd.date_range('2026-01-05 00:00',periods=50,freq='15min',tz='UTC')
    if gap:
        stamps=stamps.where(np.arange(50)<30,stamps+pd.Timedelta(minutes=15))
    h=np.full(50,102.);l=np.full(50,98.);c=np.full(50,100.)
    l[40]=95.;c[40]=99.
    frame=pd.DataFrame({'h':h,'l':l,'c':c},index=stamps)
    frame['close_at']=frame.index+pd.Timedelta(minutes=15)
    return frame

def test_frozen_grid_and_signal_confirmation():
    assert TOTAL==21600
    assert SPEC['roundtrip_all_in_usd_oz']==.4
    stamps,sides,baseline=sweep_rejections(_bars(),6,0.)
    assert len(stamps)==1 and int(sides[0])==1 and baseline[0]==4.
    assert pd.Timestamp(int(stamps[0]),unit='s',tz='UTC')==pd.Timestamp('2026-01-05 10:15Z')
    assert isinstance(canonical_signals(stamps,sides,baseline,1.,2.)[0],Signal)

def test_gap_drops_sweep_if_previous_history_not_contiguous():
    bars=_bars(gap=True)
    stamps,sides,base=sweep_rejections(bars,36,0.)
    assert len(stamps)==0

def test_gate_does_not_use_future_h1_or_stale_or_invalid_h1():
    times=np.array([1000,4000,10000],dtype=np.int64)
    sides=np.array([1,1,1],dtype=np.int8)
    base=np.array([2.,2.,2.])
    ht=np.array([500,12000],dtype=np.int64)
    trend=np.array([1,-1],dtype=np.int8)
    ratio=np.array([.5,1.5])
    masks={'ALL':np.ones(3,dtype=bool)}
    got=gate(times,sides,base,ht,trend,ratio,'WITH_H1','CALM','ALL',masks)
    assert got[0].tolist()==[1000,4000]
    got=gate(times,sides,base,ht,trend,ratio,'AGAINST_H1','CALM','ALL',masks)
    assert len(got[0])==0

def test_reject_out_of_grid():
    with pytest.raises(ValueError):sweep_rejections(_bars(),7,0.)
    with pytest.raises(ValueError):gate(np.array([],dtype=np.int64),np.array([],dtype=np.int8),np.array([]),np.array([]),np.array([]),np.array([]),'UNKNOWN','CALM','ALL')


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_frozen_sweep_same_signal_for_all_pandas_timestamp_units(unit):
    """An M15 source stored in seconds must not look like a 50-bar gap."""
    frame = _bars().copy()
    frame.index = frame.index.as_unit(unit)
    frame["close_at"] = pd.DatetimeIndex(frame["close_at"]).as_unit(unit)
    expected = sweep_rejections(_bars(), 6, 0.)
    actual = sweep_rejections(frame, 6, 0.)
    for left, right in zip(actual, expected):
        np.testing.assert_array_equal(left, right)
    assert len(actual[0]) == 1


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_frozen_sweep_missing_prior_bar_rejected_all_timestamp_units(unit):
    frame = _bars(gap=True).copy()
    frame.index = frame.index.as_unit(unit)
    frame["close_at"] = pd.DatetimeIndex(frame["close_at"]).as_unit(unit)
    assert len(sweep_rejections(frame, 36, 0.)[0]) == 0
