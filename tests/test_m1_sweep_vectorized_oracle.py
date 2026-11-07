"""Independently reconstructed loop oracle for bulk M1 sweep signals."""
import numpy as np
import pandas as pd
from norisk_quant.model import Signal
from norisk_quant.liquidity_sweep_m1 import sweep_reclaim_m1_signals


def oracle(frame, lookback, excess, reclaim, buffer, rr, max_stop):
    answer=[]
    for i in range(lookback,len(frame)):
        window=frame.iloc[i-lookback:i]
        if frame.index[i] - frame.index[i-lookback] != pd.Timedelta(minutes=lookback):
            continue
        hi,lo=window.h.max(),window.l.min()
        bar=frame.iloc[i]
        crosses_hi=bar.h > hi + excess
        crosses_lo=bar.l < lo - excess
        if crosses_hi and crosses_lo:
            continue
        if crosses_lo and lo + reclaim < bar.c < hi:
            side=1
            stop=bar.c-bar.l+buffer
        elif crosses_hi and lo < bar.c < hi - reclaim:
            side=-1
            stop=bar.h-bar.c+buffer
        else:
            continue
        if stop > max_stop:
            continue
        answer.append(Signal(frame.index[i]+pd.Timedelta(minutes=1),
                             side,float(stop),float(stop*rr),
                             f"sweep_reclaim_M1_{lookback}"))
    return answer


def test_vectorized_matches_independent_oracle_with_stress_gaps():
    rng=np.random.default_rng(9166)
    n=1400
    o=100+rng.normal(0,.4,size=n).cumsum()*.1
    c=o+rng.normal(0,.18,size=n)
    h=np.maximum(o,c)+rng.exponential(.24,n)
    l=np.minimum(o,c)-rng.exponential(.24,n)
    frame=pd.DataFrame(dict(o=o,h=h,l=l,c=c),
        index=pd.date_range("2024-03-01",periods=n,freq="min",tz="UTC"))
    # Simulate feed interruption: the prior rolling range MUST reset logically
    # until N+1 uninterrupted observed minutes have been collected.
    frame=frame.drop(frame.index[[50,51,122,499,600,601,602,900]])
    for lookback in (3,7,20,40):
        settings=dict(lookback=lookback,min_excess_usd=.15,reclaim_usd=.05,
                      stop_buffer_usd=.1,reward_risk=1.5,max_stop_usd=2.)
        expected=oracle(frame,lookback,.15,.05,.1,1.5,2.)
        actual=sweep_reclaim_m1_signals(frame,**settings)
        assert actual==expected


def test_forward_appended_bars_do_not_rewrite_prior_signal():
    rng=np.random.default_rng(217)
    n=200
    o=100+rng.normal(0,.2,n).cumsum()
    c=o+rng.normal(0,.1,n)
    h=np.maximum(o,c)+rng.exponential(.3,n)
    l=np.minimum(o,c)-rng.exponential(.3,n)
    frame=pd.DataFrame(dict(o=o,h=h,l=l,c=c),
        index=pd.date_range("2024-04-01",periods=n,freq="min",tz="UTC"))
    old=sweep_reclaim_m1_signals(frame.iloc[:90],lookback=8)
    full=sweep_reclaim_m1_signals(frame,lookback=8)
    assert old==[s for s in full if s.confirmed_at <= frame.index[89]+pd.Timedelta(minutes=1)]
