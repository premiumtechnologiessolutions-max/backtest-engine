"""FAC010 frozen research contract tests (synthetic, no private quotes in CI)."""
import numpy as np
import pandas as pd
import pytest
from scripts.batch_mad_h1_session_grid import (
    TOTAL, WINDOWS, THRESHOLDS, REGIMES, SESSIONS,
    robust_z, recovery, apply_gate, canonical_signals,
)

def _bars(closes, *, gap_after=None):
    stamps=pd.date_range('2026-01-05',periods=len(closes),freq='15min',tz='UTC')
    if gap_after is not None:
        stamps=stamps.where(np.arange(len(stamps))<=gap_after,stamps+pd.Timedelta(minutes=15))
    bars=pd.DataFrame({'c':np.asarray(closes,dtype=float)},index=stamps)
    bars['close_at']=bars.index+pd.Timedelta(minutes=15)
    return bars

def test_frozen_grid_is_20736_specs_not_independent_hypotheses():
    assert len(WINDOWS)*len(THRESHOLDS)*len(REGIMES)*len(SESSIONS)*12*12==TOTAL==20736

def test_robust_z_uses_previous_closes_only():
    close=np.array([100.,101.,102.,103.,104.,105.,106.,107.,108.,109.,110.,111.,112.,113.])
    segment=np.zeros(len(close),dtype=np.int64)
    before=robust_z(close,segment,12)
    changed=close.copy();changed[-1]=500.
    after=robust_z(changed,segment,12)
    assert np.isnan(before[:12]).all()
    assert before[12]==after[12]  # future modification cannot change prior bar
    assert after[13]!=before[13]

def test_gap_resets_mad_history():
    close=np.linspace(100.,120.,70)
    contiguous=recovery(_bars(close),12,1.25)
    broken=recovery(_bars(close,gap_after=30),12,1.25)
    assert len(contiguous)==2 and len(broken)==2
    z=robust_z(close,np.cumsum(np.r_[True,np.diff(_bars(close,gap_after=30).index.asi8)!=900_000_000_000]).astype(np.int64),12)
    assert np.isnan(z[31:43]).all()

def test_session_gate_is_fixed_utc_and_h1_closed_only():
    times=np.array([int(pd.Timestamp('2026-01-05 07:00',tz='UTC').timestamp()),
                    int(pd.Timestamp('2026-01-05 15:00',tz='UTC').timestamp())],dtype=np.int64)
    sides=np.array([1,-1],dtype=np.int8)
    h1times=times.copy()
    ratios=np.array([.7,.7])
    t,s=apply_gate(times,sides,h1times,ratios,'QUIET085','EU_FIXED_UTC')
    assert t.tolist()==[times[0]] and s.tolist()==[1]
    t,_=apply_gate(times,sides,h1times,ratios,'HOT115','ALL')
    assert len(t)==0

def test_stale_h1_and_nonfrozen_gate_rejected():
    now=int(pd.Timestamp('2026-01-05 08:00',tz='UTC').timestamp())
    times=np.array([now],dtype=np.int64)
    sides=np.array([1],dtype=np.int8)
    t,_=apply_gate(times,sides,np.array([now-3660],dtype=np.int64),
                   np.array([.7]),'QUIET085','ALL')
    assert len(t)==0
    with pytest.raises(ValueError):
        apply_gate(times,sides,np.array([now]),np.array([1.]),'UNKNOWN','ALL')
    with pytest.raises(ValueError):
        recovery(_bars(np.linspace(100.,110.,30)),13,1.25)

def test_canonical_signals_fee_and_utc_contract():
    times=np.array([int(pd.Timestamp('2026-01-05 08:00',tz='UTC').timestamp())],dtype=np.int64)
    signals=canonical_signals(times,np.array([-1],dtype=np.int8),2.,3.)
    assert len(signals)==1 and signals[0].side==-1
    assert signals[0].confirmed_at.tzinfo is not None
    assert signals[0].stop_distance==2. and signals[0].target_distance==3.
