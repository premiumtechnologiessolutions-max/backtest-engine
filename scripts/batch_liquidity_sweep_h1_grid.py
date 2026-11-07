"""FAC013 frozen M15 prior-extreme liquidity-sweep rejection / completed H1 gate.

Preregistration: d1efaa8dc43b61583f0c2aee45460ea59123bd1f.
2012/2013 exposed design years, NOT OOS. Original BID/ASK ZIP stays local.
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
from scripts.batch_donchian_grid import HAS_JIT, ORIGINAL
from scripts.batch_compression_h1_grid import h1_context, local_session_masks, replay_normalized

LOOKBACKS = (6, 12, 24, 36)
SWEEPS = (0., .25, .5)
MODES = ('WITH_H1', 'AGAINST_H1', 'IGNORE_H1')
REGIMES = ('CALM', 'ACTIVE')
SESSIONS = ('ALL', 'LONDON_LOCAL_08_12', 'NY_LOCAL_0930_1330')
MULTS = tuple(.5 + .25*i for i in range(10))
TOTAL = len(LOOKBACKS)*len(SWEEPS)*len(MODES)*len(REGIMES)*len(SESSIONS)*len(MULTS)**2
PREREG = 'd1efaa8dc43b61583f0c2aee45460ea59123bd1f'
SPEC = {'research_id':'NRF-FAC-013','preregistration_commit':PREREG,
        'lookbacks':list(LOOKBACKS),'sweep_mults':list(SWEEPS),'h1_modes':list(MODES),
        'regimes':list(REGIMES),'sessions':list(SESSIONS),
        'stop_mults':list(MULTS),'target_mults':list(MULTS),'specs_per_year':TOTAL,
        'years':[2012,2013],'original_source_sha256':ORIGINAL,'roundtrip_all_in_usd_oz':.4,
        'historically_exposed_not_oos':True}

def sweep_rejections(m15, lookback, minimum_sweep):
    """Only completed M15 j vs contiguous previous N and previous 20 M15 bars."""
    if lookback not in LOOKBACKS or minimum_sweep not in SWEEPS:
        raise ValueError('Nonfrozen liquidity-sweep settings')
    if len(m15)<max(lookback,20)+1:
        return np.empty(0,np.int64),np.empty(0,np.int8),np.empty(0,float)
    h,l,c=(m15[k].to_numpy(float) for k in ('h','l','c'))
    # Pandas DatetimeIndex.asi8 follows the index's own unit (s/ms/us/ns).
    # Compare elapsed M15 intervals in normalized nanoseconds.
    segment=np.cumsum(np.r_[True,np.diff(m15.index.as_unit('ns').asi8)!=900_000_000_000])
    prior_n_high=pd.Series(h).shift(1).rolling(lookback,min_periods=lookback).max().to_numpy()
    prior_n_low=pd.Series(l).shift(1).rolling(lookback,min_periods=lookback).min().to_numpy()
    base=pd.Series(h-l).shift(1).rolling(20,min_periods=20).median().to_numpy()
    idx=np.arange(len(m15))
    back=max(lookback,20)
    valid=(idx>=back)&(segment==segment[np.maximum(idx-back,0)])
    valid &= np.isfinite(base)&(base>0)&np.isfinite(prior_n_high)&np.isfinite(prior_n_low)
    long=valid&(l<prior_n_low-minimum_sweep*base)&(c>prior_n_low)&(c<prior_n_high)
    short=valid&(h>prior_n_high+minimum_sweep*base)&(c<prior_n_high)&(c>prior_n_low)
    selected=np.flatnonzero(long^short)
    stamps=np.asarray(m15.close_at.array.as_unit('ns').asi8//1_000_000_000,dtype=np.int64)
    return stamps[selected],np.where(long[selected],1,-1).astype(np.int8),base[selected]

def gate(times,sides,base,h1times,h1trend,h1ratio,mode,regime,session,masks=None):
    if mode not in MODES or regime not in REGIMES or session not in SESSIONS:
        raise ValueError('Nonfrozen context gate')
    if len(times)!=len(sides) or len(times)!=len(base):
        raise ValueError('Mismatched signals')
    if not len(times) or not len(h1times):
        return times[:0],sides[:0],base[:0]
    pos=np.searchsorted(h1times,times,side='right')-1
    safe=np.maximum(pos,0)
    age=times-h1times[safe]
    valid=(pos>=0)&(age>=0)&(age<=3600)&np.isfinite(h1ratio[safe])&(h1trend[safe]!=0)
    if regime=='CALM':valid &= h1ratio[safe]<=1.
    else:valid &= h1ratio[safe]>1.
    if mode=='WITH_H1':valid &= sides==h1trend[safe]
    elif mode=='AGAINST_H1':valid &= sides==-h1trend[safe]
    if masks is None:masks=local_session_masks(times)
    valid &= masks[session]
    return times[valid],sides[valid],base[valid]

def canonical_signals(times,sides,base,stop_mult,target_mult):
    return [Signal(pd.Timestamp(int(t),unit='s',tz='UTC'),int(s),float(v*stop_mult),
                   float(v*target_mult),'FAC013_M15_SWEEP_H1')
            for t,s,v in zip(times,sides,base)]

def run_batch(m1,year,out,limit=TOTAL):
    if type(year) is not int or year not in (2012,2013) or type(limit) is not int or not 1<=limit<=TOTAL:
        raise ValueError('Outside frozen FAC013 grid')
    if limit>100 and not HAS_JIT:raise RuntimeError('Numba required for bulk')
    out=Path(out)
    if (out/'summary.json').exists():raise FileExistsError('Refuse completed experiment overwrite')
    out.mkdir(parents=True,exist_ok=True)
    frozen=out/'frozen_spec.json'
    if frozen.exists() and json.loads(frozen.read_text())!=SPEC:raise ValueError('Conflicting spec')
    frozen.write_text(json.dumps(SPEC,indent=2),encoding='utf-8')
    start=time.perf_counter()
    m15=aggregate_bars(m1,'M15');h1=aggregate_bars(m1,'H1')
    ht,trend,ratio=h1_context(h1)
    stamps=np.asarray(m1.index.as_unit('ns').asi8//1_000_000_000,dtype=np.int64)
    op,hi,lo,cl=(m1[k].to_numpy(float) for k in ('o','h','l','c'))
    months=(m1.index.month.to_numpy(np.int16)-1).astype(np.int8)
    rows=[];cache={};hashes=set()
    for lookback,sweep in itertools.product(LOOKBACKS,SWEEPS):
        times,sides,base=sweep_rejections(m15,lookback,sweep)
        masks=local_session_masks(times)
        for mode,regime,session in itertools.product(MODES,REGIMES,SESSIONS):
            st,sd,sb=gate(times,sides,base,ht,trend,ratio,mode,regime,session,masks)
            key=(lookback,sweep,mode,regime,session)
            cache[key]=(st,sd,sb)
            hashes.add(hashlib.sha256(st.tobytes()+sd.tobytes()+sb.tobytes()).hexdigest())
            for stop,target in itertools.product(MULTS,MULTS):
                if len(rows)>=limit:break
                monthly,n,net,fees,dd,expired=replay_normalized(
                    stamps,op,hi,lo,cl,months,st,sd,sb,float(stop),float(target))
                ident=f'SWEEP15_N{lookback:02d}_K{sweep:.2f}_{mode}_{regime}_{session}_SL{stop:.2f}_TP{target:.2f}'
                rows.append((ident,lookback,sweep,mode,regime,session,stop,target,len(st),expired,
                             n,net,fees,dd,int((monthly>0).sum()),float(monthly.min()),*monthly.tolist()))
            if len(rows)>=limit:break
        if len(rows)>=limit:break
    cols=['id','lookback','sweep','mode','regime','session','stop_mult','target_mult','signals',
          'expired','trades','net_usd_oz','fees_usd','max_m1_dd','positive_months','worst_month']+[
              f'm{i:02d}' for i in range(1,13)]
    table=pd.DataFrame(rows,columns=cols)
    if not table.id.is_unique:raise AssertionError('Duplicate parameter IDs')
    ranked=table.sort_values(['positive_months','worst_month','net_usd_oz'],ascending=[False,False,False])
    picks=sorted(set([0,len(table)//2,len(table)-1,int(ranked.index[0])]))
    parity=[]
    for ix in picks:
        row=table.iloc[ix]
        st,sd,sb=cache[(int(row.lookback),float(row.sweep),row['mode'],row.regime,row.session)]
        ref=run_fast(m1,canonical_signals(st,sd,sb,row.stop_mult,row.target_mult),
                     Settings(ounces=1.,roundtrip_cost_per_ounce=.4))
        booked=np.bincount(pd.to_datetime(ref.trades.closed_at,utc=True).dt.month,
                           weights=ref.trades.net_pnl.to_numpy(float),minlength=13)[1:]
        expected=row[[f'm{i:02d}' for i in range(1,13)]].to_numpy(float)
        delta=float(np.max(np.abs(booked-expected)))
        marked=ref.equity.equity
        dd=float((marked.cummax().clip(lower=0)-marked).clip(lower=0).max())
        if delta>1e-7 or abs(dd-row.max_m1_dd)>1e-7 or len(ref.trades)!=row.trades or abs(ref.trades.net_pnl.sum()-row.net_usd_oz)>1e-7 or abs(ref.trades.cost.sum()-row.fees_usd)>1e-7:
            raise AssertionError(f'Canonical mismatch: {row.id}: month={delta}, dd={dd-row.max_m1_dd}')
        parity.append({'id':row.id,'trades':int(row.trades),'monthly_max_error':delta,
                       'floating_dd_error':abs(dd-row.max_m1_dd)})
    table.to_csv(out/'all_candidates_monthly.csv',index=False)
    ranked.head(20).to_csv(out/'exploratory_top20_NOT_OOS.csv',index=False)
    summary={'status':'COMPLETED_EXPOSED_DESIGN_NOT_OOS','year':year,'executed_annual_replays':len(table),
             'active_annual_replays':int((table.trades>0).sum()),'zero_trade_replays':int((table.trades==0).sum()),
             'monthly_points':len(table)*12,'unique_signal_streams':len(hashes),
             'positive_annual_net_specs':int((table.net_usd_oz>0).sum()),
             'max_positive_months':int(table.positive_months.max()),
             'configs_12_of_12':int((table.positive_months==12).sum()),
             'original_source_sha256':ORIGINAL,'loaded_m1_sha256':fingerprint_loaded_m1(m1),
             'canonical_run_fast_parity':parity,'elapsed_seconds':round(time.perf_counter()-start,2),
             'warning':'Historically exposed 2012-2013; correlated grid, not independent OOS.'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return table,summary

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gold-zip',type=Path,required=True)
    p.add_argument('--year',type=int,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--limit',type=int,default=TOTAL)
    args=p.parse_args()
    if sha256_file(args.gold_zip)!=ORIGINAL:raise ValueError('Original ZIP SHA mismatch')
    m1=load_market(args.gold_zip,f'{args.year}-01-01',f'{args.year}-12-31')
    print(json.dumps(run_batch(m1,args.year,args.out,args.limit)[1],indent=2))
if __name__=='__main__':main()
