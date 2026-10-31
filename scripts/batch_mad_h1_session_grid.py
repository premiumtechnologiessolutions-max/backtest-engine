"""FAC010 preregistered M15 robust-MAD recovery / H1 range regime / fixed UTC sessions.

Private original Gold data.zip must remain local. Design years exposed, NOT OOS.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from norisk_quant.data import load_market, sha256_file, fingerprint_loaded_m1
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import ORIGINAL, HAS_JIT, njit, replay_core
from scripts.batch_h1_range_ema_grid import h1_range_relative

WINDOWS=(12,20,32,48)
THRESHOLDS=(1.25,1.75,2.25,2.75)
REGIMES=('QUIET085','QUIET115','HOT115')
SESSIONS=('ALL','EU_FIXED_UTC','US_FIXED_UTC')
STOPS=tuple(1.+.5*i for i in range(12))
TARGETS=tuple(.5+.5*i for i in range(12))
TOTAL=20736
SPEC={'id':'NRF-FAC-010','frozen_document':'docs/FAC010_FROZEN_MAD_H1_SESSION_2026-10-26.md',
      'windows':list(WINDOWS),'thresholds':list(THRESHOLDS),'regimes':list(REGIMES),
      'sessions':list(SESSIONS),'stops':list(STOPS),'targets':list(TARGETS),
      'design_years':[2012,2013],'specs_per_year':TOTAL,'source_sha256':ORIGINAL,
      'fee_all_in_usd_oz':.4,'historically_exposed_not_oos':True}

@njit(cache=True)
def robust_z(close,segment,window):
    """Completed close vs previous W completed closes, reset at gaps."""
    z=np.full(len(close),np.nan,np.float64)
    for i in range(window,len(close)):
        if segment[i]!=segment[i-window]:
            continue
        prior=close[i-window:i]
        med=np.median(prior)
        mad=np.median(np.abs(prior-med))
        if mad>0. and np.isfinite(mad):
            z[i]=(close[i]-med)/(1.4826*mad)
    return z

def recovery(bars,window,threshold):
    if window not in WINDOWS or threshold not in THRESHOLDS:
        raise ValueError('Non-frozen window/threshold')
    if bars.empty:
        return np.empty(0,np.int64),np.empty(0,np.int8)
    segment=np.cumsum(np.r_[True,np.diff(bars.index.asi8)!=900_000_000_000]).astype(np.int64)
    z=robust_z(bars.c.to_numpy(dtype=np.float64),segment,window)
    previous=np.r_[np.nan,z[:-1]]
    valid=np.r_[False,segment[1:]==segment[:-1]] & np.isfinite(z) & np.isfinite(previous)
    longs=valid&(previous<=-threshold)&(z>-threshold)
    shorts=valid&(previous>=threshold)&(z<threshold)
    keep=np.flatnonzero(longs|shorts)
    return (np.asarray(bars.close_at.iloc[keep].array.asi8//1_000_000_000,dtype=np.int64),
            np.where(longs[keep],1,-1).astype(np.int8))

def apply_gate(times,sides,h1times,ratios,regime,session):
    if regime not in REGIMES or session not in SESSIONS:
        raise ValueError('Non-frozen regime/session')
    if len(times)!=len(sides) or len(h1times)!=len(ratios):
        raise ValueError('Mismatched arrays')
    if not len(times) or not len(h1times):
        return np.empty(0,np.int64),np.empty(0,np.int8)
    last=np.searchsorted(h1times,times,side='right')-1
    safe=np.maximum(last,0)
    age=times-h1times[safe]
    valid=(last>=0)&(age>=0)&(age<=3600)&np.isfinite(ratios[safe])
    if regime=='QUIET085': valid &= ratios[safe]<=.85
    elif regime=='QUIET115': valid &= ratios[safe]<=1.15
    else: valid &= ratios[safe]>=1.15
    hour=(times//3600)%24
    if session=='EU_FIXED_UTC':valid &= (hour>=7)&(hour<15)
    elif session=='US_FIXED_UTC':valid &= (hour>=13)&(hour<21)
    return times[valid],sides[valid]

def canonical_signals(times,sides,stop,target):
    return [Signal(pd.Timestamp(int(t),unit='s',tz='UTC'),int(side),float(stop),float(target),
                   'FAC010_MAD15_H1_SESSION') for t,side in zip(times,sides)]

def run_batch(m1,year,out,limit=TOTAL):
    if year not in (2012,2013) or type(limit) is not int or not 1<=limit<=TOTAL:
        raise ValueError('Outside frozen scope')
    if limit>100 and not HAS_JIT:
        raise RuntimeError('Full sweep requires optional Numba')
    out=Path(out)
    if (out/'summary.json').exists():raise FileExistsError('Refuse overwrite of completed experiment')
    out.mkdir(parents=True,exist_ok=True)
    frozen=out/'frozen_spec.json'
    if frozen.exists() and json.loads(frozen.read_text())!=SPEC:
        raise ValueError('Conflicting frozen specification')
    frozen.write_text(json.dumps(SPEC,indent=2),encoding='utf-8')
    started=time.perf_counter()
    m15=aggregate_bars(m1,'M15')
    h1=aggregate_bars(m1,'H1')
    ratios=h1_range_relative(h1)
    h1times=np.asarray(h1.close_at.array.asi8//1_000_000_000,dtype=np.int64)
    stamps=np.asarray(m1.index.asi8//1_000_000_000,dtype=np.int64)
    op,hi,lo,cl=(m1[k].to_numpy(dtype=float) for k in ('o','h','l','c'))
    months=(m1.index.month.to_numpy(dtype=np.int16)-1).astype(np.int8)
    rows=[]; cache={}; hashes=set()
    for window,threshold in itertools.product(WINDOWS,THRESHOLDS):
        times,sides=recovery(m15,window,threshold)
        for regime,session in itertools.product(REGIMES,SESSIONS):
            st,sd=apply_gate(times,sides,h1times,ratios,regime,session)
            cache[(window,threshold,regime,session)]=(st,sd)
            hashes.add(hashlib.sha256(st.tobytes()+sd.tobytes()).hexdigest())
            for stop,target in itertools.product(STOPS,TARGETS):
                if len(rows)>=limit:break
                monthly,trades,net,fees,dd,expired=replay_core(
                    stamps,op,hi,lo,cl,months,st,sd,float(stop),float(target))
                ident=f'MAD15_W{window:02d}_Z{threshold:.2f}_{regime}_{session}_SL{stop:.2f}_TP{target:.2f}'
                rows.append((ident,window,threshold,regime,session,stop,target,len(st),expired,
                             trades,net,fees,dd,int((monthly>0).sum()),float(monthly.min()),*monthly.tolist()))
            if len(rows)>=limit:break
        if len(rows)>=limit:break
    cols=['id','window','threshold','regime','session','stop_usd','target_usd','signals','expired',
          'trades','net_usd_oz','fees_usd','max_m1_dd','positive_months','worst_month']+[
              f'm{i:02d}' for i in range(1,13)]
    table=pd.DataFrame(rows,columns=cols)
    if not table.id.is_unique:raise AssertionError('Duplicate parameter IDs')
    parity=[]
    for row in table.iloc[sorted(set([0,len(table)//2,len(table)-1]))].itertuples(index=False):
        st,sd=cache[(row.window,row.threshold,row.regime,row.session)]
        ref=run_fast(m1,canonical_signals(st,sd,row.stop_usd,row.target_usd),
                     Settings(ounces=1.,roundtrip_cost_per_ounce=.4))
        booked=np.bincount(pd.to_datetime(ref.trades.closed_at,utc=True).dt.month,
                           weights=ref.trades.net_pnl.to_numpy(),minlength=13)[1:]
        expected=np.array([getattr(row,f'm{i:02d}') for i in range(1,13)])
        month_error=float(np.max(np.abs(booked-expected)))
        marked=ref.equity.equity
        dd=float((marked.cummax().clip(lower=0)-marked).clip(lower=0).max())
        dd_error=abs(dd-row.max_m1_dd)
        if (month_error>1e-7 or dd_error>1e-7 or len(ref.trades)!=row.trades or
            abs(ref.trades.net_pnl.sum()-row.net_usd_oz)>1e-7 or
            abs(ref.trades.cost.sum()-row.fees_usd)>1e-7):
            raise AssertionError(f'Official run_fast parity failed {row.id}')
        parity.append({'id':row.id,'trades':int(row.trades),
                       'max_month_error':month_error,'floating_dd_error':dd_error})
    table.to_csv(out/'all_candidates_monthly.csv',index=False)
    table.sort_values(['positive_months','worst_month','net_usd_oz'],
                      ascending=[False,False,False]).head(20).to_csv(out/'exploratory_top20_NOT_OOS.csv',index=False)
    summary={'status':'COMPLETED_EXPOSED_DESIGN_NOT_OOS','year':year,
        'executed_specs':len(table),'unique_entry_signal_sequences':len(hashes),
        'zero_trade_specs':int((table.trades==0).sum()),
        'positive_annual_net_specs':int((table.net_usd_oz>0).sum()),
        'max_positive_months':int(table.positive_months.max()),
        'positive_12_months':int((table.positive_months==12).sum()),
        'm1_rows':len(m1),'complete_m15_bars':len(m15),'complete_h1_bars':len(h1),
        'loaded_m1_sha256':fingerprint_loaded_m1(m1),
        'original_zip_sha256':ORIGINAL,'official_run_fast_parity':parity,
        'elapsed_seconds':round(time.perf_counter()-started,3),
        'warning':'Exposed historical design, correlated parameters, not independent OOS.'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return table,summary

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gold-zip',type=Path,required=True)
    p.add_argument('--year',type=int,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--limit',type=int,default=TOTAL)
    a=p.parse_args()
    if sha256_file(a.gold_zip)!=ORIGINAL:raise ValueError('Original Gold data.zip SHA mismatch')
    m1=load_market(a.gold_zip,f'{a.year}-01-01',f'{a.year}-12-31')
    print(json.dumps(run_batch(m1,a.year,a.out,a.limit)[1],indent=2))
if __name__=='__main__':main()
