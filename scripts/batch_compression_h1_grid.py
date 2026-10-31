"""NRF-FAC-012B: frozen M15 compression breakout, H1 EMA and volatility halt.

Gap-aware preregistration commit bee2e7f072b9a44a2592d007f2dd3fb7d41c23f7.
Only SHA-verified private XAUUSD ZIP may be replayed locally. Exposed years,
correlated specs, no clean OOS, no real fills, no monthly-profit guarantee.
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

from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import HAS_JIT, ORIGINAL, njit

LOOKBACKS = (4, 6, 8, 12, 16)
SQUEEZES = (.55, .75, .95, 1.15)
MODES = ('ALIGNED', 'CONTRA')
VOL_HALTS = (1.2, 1.8)
SESSIONS = ('ALL', 'LONDON_LOCAL_08_12', 'NY_LOCAL_0930_1330')
MULTS = tuple(.5 + .25*i for i in range(10))
TOTAL = len(LOOKBACKS)*len(SQUEEZES)*len(MODES)*len(VOL_HALTS)*len(SESSIONS)*len(MULTS)**2
PREREG = 'bee2e7f072b9a44a2592d007f2dd3fb7d41c23f7'
SPEC = {
    'research_id': 'NRF-FAC-012B', 'preregistration_commit': PREREG,
    'family': 'M15 compression-breakout with H1 EMA trend and prior-known volatility halt',
    'lookbacks': list(LOOKBACKS), 'squeezes': list(SQUEEZES),
    'modes': list(MODES), 'vol_halts': list(VOL_HALTS),
    'sessions': list(SESSIONS), 'stop_mults': list(MULTS),
    'target_mults': list(MULTS), 'specs_per_year': TOTAL,
    'years': [2012, 2013], 'source_sha256': ORIGINAL,
    'roundtrip_all_in_usd_per_oz': .4,
    'historically_exposed_not_oos': True,
}

def compression_breaks(m15, lookback, squeeze):
    """Previous bar squeeze vs j-21..j-2; current closed j breaks prior N."""
    if lookback not in LOOKBACKS or squeeze not in SQUEEZES:
        raise ValueError('Non-frozen compression parameters')
    if len(m15) < 22:
        return np.empty(0,np.int64),np.empty(0,np.int8),np.empty(0,float)
    # Compare M15 intervals in nanoseconds regardless of source index unit.
    segment = np.cumsum(np.r_[True,np.diff(m15.index.as_unit('ns').asi8)!=900_000_000_000])
    high=m15.h.to_numpy(float);low=m15.l.to_numpy(float);close=m15.c.to_numpy(float)
    ranges=high-low
    baseline=pd.Series(ranges).shift(2).rolling(20,min_periods=20).median().to_numpy()
    previous_high=pd.Series(high).shift(1).rolling(lookback,min_periods=lookback).max().to_numpy()
    previous_low=pd.Series(low).shift(1).rolling(lookback,min_periods=lookback).min().to_numpy()
    indices=np.arange(len(m15))
    eligible=(indices>=21)&(segment==segment[np.maximum(0,indices-21)])
    eligible &= np.isfinite(baseline)&(baseline>0)
    eligible &= np.r_[False,ranges[:-1]>0]
    eligible &= np.r_[np.nan,ranges[:-1]]<=squeeze*baseline
    up=eligible&(close>previous_high)
    down=eligible&(close<previous_low)
    selected=np.flatnonzero(up|down)
    stamps=np.asarray(m15.close_at.array.as_unit('ns').asi8//1_000_000_000,dtype=np.int64)
    return stamps[selected],np.where(up[selected],1,-1).astype(np.int8),baseline[selected]

def h1_context(h1):
    """Observed completed H1 only; EMA and previous24 range within 168h."""
    if h1.empty:
        return np.empty(0,np.int64),np.empty(0,np.int8),np.empty(0,float)
    stamps=np.asarray(h1.close_at.array.as_unit('ns').asi8//1_000_000_000,dtype=np.int64)
    segment=np.cumsum(np.r_[True,np.diff(stamps)>168*3600])
    groups=pd.Series(segment,index=h1.index)
    close=h1.c.astype(float)
    ema8=close.groupby(groups).transform(lambda g:g.ewm(span=8,adjust=False).mean()).to_numpy()
    ema24=close.groupby(groups).transform(lambda g:g.ewm(span=24,adjust=False).mean()).to_numpy()
    indices=np.arange(len(h1))
    warm=(close.groupby(groups).cumcount().to_numpy()>=25)
    warm &= (stamps-stamps[np.maximum(0,indices-25)])<=168*3600
    trend=np.where(ema8>ema24,1,np.where(ema8<ema24,-1,0)).astype(np.int8)
    trend[~warm]=0
    ranges=(h1.h-h1.l).to_numpy(float)
    previous=pd.Series(ranges).shift(1).rolling(24,min_periods=24).median().to_numpy()
    valid=(indices>=24)&(segment==segment[np.maximum(0,indices-24)])
    valid &= (stamps-stamps[np.maximum(0,indices-24)])<=168*3600
    valid &= np.isfinite(previous)&(previous>0)&(ranges>0)&(trend!=0)
    ratio=np.full(len(h1),np.nan)
    ratio[valid]=ranges[valid]/previous[valid]
    return stamps,trend,ratio

def local_session_masks(times):
    utc=pd.to_datetime(times,unit='s',utc=True)
    london=utc.tz_convert('Europe/London')
    ny=utc.tz_convert('America/New_York')
    lm=np.asarray(london.hour*60+london.minute)
    nm=np.asarray(ny.hour*60+ny.minute)
    return {'ALL':np.ones(len(times),dtype=bool),
            'LONDON_LOCAL_08_12':(lm>=480)&(lm<720),
            'NY_LOCAL_0930_1330':(nm>=570)&(nm<810)}

def causal_gate(times,sides,baseline,h1times,h1trend,h1ratio,mode,halt,session,masks=None):
    if mode not in MODES or halt not in VOL_HALTS or session not in SESSIONS:
        raise ValueError('Non-frozen gate')
    if len(times)!=len(sides) or len(times)!=len(baseline):
        raise ValueError('Mismatched signal arrays')
    if not len(times) or not len(h1times):
        return np.empty(0,np.int64),np.empty(0,np.int8),np.empty(0,float)
    last=np.searchsorted(h1times,times,side='right')-1
    safe=np.maximum(0,last)
    age=times-h1times[safe]
    if masks is None:masks=local_session_masks(times)
    valid=(last>=0)&(age>=0)&(age<=3600)&np.isfinite(h1ratio[safe])
    valid &= (h1ratio[safe]<=halt)&masks[session]
    expected=sides if mode=='ALIGNED' else -sides
    valid &= h1trend[safe]==expected
    return times[valid],expected[valid].astype(np.int8),baseline[valid]

@njit(cache=True)
def replay_normalized(stamps,op,hi,lo,cl,months,signalt,signs,vols,stop_mult,target_mult):
    """Single 1oz position, exact fee .4, M1 floating marks, stop-first."""
    count=len(stamps);pointer=0;next_free=0;trades=0;expired=0
    monthly=np.zeros(12,np.float64)
    realized=0.;fees=0.;peak=0.;max_dd=0.
    while next_free<count and pointer<len(signalt):
        confirmed=signalt[pointer]
        at=np.searchsorted(stamps,confirmed)
        if at<next_free:at=next_free
        if at>=count:break
        if stamps[at]-confirmed>60:
            pointer+=1;expired+=1;continue
        direction=signs[pointer]
        stopdist=vols[pointer]*stop_mult
        targetdist=vols[pointer]*target_mult
        pointer+=1
        price=op[at];stop=price-direction*stopdist;target=price+direction*targetdist
        entry=at;exited=False
        while at<count:
            opening=op[at];high=hi[at];low=lo[at]
            if at>entry:
                if (direction==1 and opening<=stop) or (direction==-1 and opening>=stop):
                    exit_price=opening;exited=True
                elif (direction==1 and opening>=target) or (direction==-1 and opening<=target):
                    exit_price=target;exited=True
            if not exited:
                stop_hit=low<=stop if direction==1 else high>=stop
                target_hit=high>=target if direction==1 else low<=target
                if stop_hit:
                    exit_price=stop;exited=True
                elif target_hit:
                    exit_price=target;exited=True
            if exited:
                pnl=direction*(exit_price-price)-.4
                realized+=pnl;monthly[months[at]]+=pnl;trades+=1;fees+=.4
                if realized>peak:peak=realized
                dd=peak-realized
                if dd>max_dd:max_dd=dd
                next_free=at+1
                break
            marked=realized+direction*(cl[at]-price)-.4
            if marked>peak:peak=marked
            dd=peak-marked
            if dd>max_dd:max_dd=dd
            at+=1
        if not exited:
            last=count-1
            pnl=direction*(cl[last]-price)-.4
            realized+=pnl;monthly[months[last]]+=pnl;trades+=1;fees+=.4
            if realized>peak:peak=realized
            dd=peak-realized
            if dd>max_dd:max_dd=dd
            next_free=count
    return monthly,trades,realized,fees,max_dd,expired

def canonical_signals(times,sides,vols,sm,tm):
    return [Signal(pd.Timestamp(int(t),unit='s',tz='UTC'),int(s),
                   float(v*sm),float(v*tm),'FAC012B_COMPRESSION_H1')
            for t,s,v in zip(times,sides,vols)]

def run_batch(m1,year,out,limit=TOTAL):
    if type(year) is not int or year not in (2012,2013):
        raise ValueError('Frozen years only')
    if type(limit) is not int or not 1<=limit<=TOTAL:
        raise ValueError('Invalid frozen limit')
    if limit>100 and not HAS_JIT:
        raise RuntimeError('Numba required for bulk')
    out=Path(out)
    if (out/'summary.json').exists():
        raise FileExistsError('Refuse overwrite of completed experiment')
    out.mkdir(parents=True,exist_ok=True)
    frozen=out/'frozen_spec.json'
    if frozen.exists() and json.loads(frozen.read_text())!=SPEC:
        raise ValueError('Conflicting frozen spec')
    frozen.write_text(json.dumps(SPEC,indent=2),encoding='utf-8')
    started=time.perf_counter()
    m15=aggregate_bars(m1,'M15');h1=aggregate_bars(m1,'H1')
    ht,trend,ratio=h1_context(h1)
    stamps=np.asarray(m1.index.as_unit('ns').asi8//1_000_000_000,dtype=np.int64)
    op,hi,lo,cl=(m1[k].to_numpy(float) for k in ('o','h','l','c'))
    months=(m1.index.month.to_numpy(np.int16)-1).astype(np.int8)
    rows=[];cache={};hashes=set()
    for n,squeeze in itertools.product(LOOKBACKS,SQUEEZES):
        bt,bs,bv=compression_breaks(m15,n,squeeze)
        masks=local_session_masks(bt)
        for mode,halt,session in itertools.product(MODES,VOL_HALTS,SESSIONS):
            t,s,v=causal_gate(bt,bs,bv,ht,trend,ratio,mode,halt,session,masks)
            cache[(n,squeeze,mode,halt,session)]=(t,s,v)
            hashes.add(hashlib.sha256(t.tobytes()+s.tobytes()+v.tobytes()).hexdigest())
            for sm,tm in itertools.product(MULTS,MULTS):
                if len(rows)>=limit:break
                monthly,trades,net,fees,dd,expired=replay_normalized(
                    stamps,op,hi,lo,cl,months,t,s,v,float(sm),float(tm))
                ident=f'COMP15_N{n:02d}_Q{squeeze:.2f}_{mode}_H{halt:.2f}_{session}_SL{sm:.2f}_TP{tm:.2f}'
                rows.append((ident,n,squeeze,mode,halt,session,sm,tm,len(t),expired,
                             trades,net,fees,dd,int((monthly>0).sum()),float(monthly.min()),*monthly.tolist()))
            if len(rows)>=limit:break
        if len(rows)>=limit:break
    cols=['id','lookback','squeeze','mode','h1_vol_halt','session','stop_mult','target_mult',
          'signals','expired','trades','net_usd_oz','fees_usd','max_m1_dd','positive_months',
          'worst_month']+[f'm{i:02d}' for i in range(1,13)]
    table=pd.DataFrame(rows,columns=cols)
    if not table.id.is_unique:raise AssertionError('Duplicate parameter IDs')
    if not np.allclose(table.net_usd_oz,table[[f'm{i:02d}' for i in range(1,13)]].sum(axis=1),atol=1e-7):
        raise AssertionError('Monthly P/L mismatch')
    if not np.allclose(table.fees_usd,.4*table.trades,atol=1e-7):
        raise AssertionError('Fee mismatch')
    parity=[]
    picks=sorted(set(np.linspace(0,len(table)-1,min(5,len(table)),dtype=int)))
    for row in table.iloc[picks].itertuples(index=False):
        t,s,v=cache[(row.lookback,row.squeeze,row.mode,row.h1_vol_halt,row.session)]
        ref=run_fast(m1,canonical_signals(t,s,v,row.stop_mult,row.target_mult),
                     Settings(ounces=1.,roundtrip_cost_per_ounce=.4))
        booked=np.bincount(pd.to_datetime(ref.trades.closed_at,utc=True).dt.month,
                           weights=ref.trades.net_pnl.to_numpy(),minlength=13)[1:]
        expected=np.array([getattr(row,f'm{i:02d}') for i in range(1,13)])
        month_error=float(np.max(np.abs(booked-expected)))
        equity=ref.equity.equity
        ref_dd=float((equity.cummax().clip(lower=0)-equity).clip(lower=0).max())
        dd_error=abs(ref_dd-row.max_m1_dd)
        if month_error>1e-7 or dd_error>1e-7 or len(ref.trades)!=row.trades or abs(ref.trades.net_pnl.sum()-row.net_usd_oz)>1e-7 or abs(ref.trades.cost.sum()-row.fees_usd)>1e-7:
            raise AssertionError(f'Canonical parity failed {row.id}')
        parity.append({'id':row.id,'trades':int(row.trades),
                       'max_month_error':month_error,'dd_error':dd_error})
    table.to_csv(out/'all_candidates_monthly.csv',index=False)
    table.sort_values(['positive_months','worst_month','net_usd_oz'],
                      ascending=[False,False,False]).head(20).to_csv(out/'exploratory_top20_NOT_OOS.csv',index=False)
    summary={'status':'COMPLETED_EXPOSED_DESIGN_NOT_OOS','year':year,
        'executed_annual_replays':len(table),'active_annual_replays':int((table.trades>0).sum()),
        'zero_trade_replays':int((table.trades==0).sum()),'monthly_points':len(table)*12,
        'positive_annual_net':int((table.net_usd_oz>0).sum()),
        'max_positive_months':int(table.positive_months.max()),
        'configs_12_of_12':int((table.positive_months==12).sum()),
        'unique_signal_streams':len(hashes),'m1_rows':len(m1),
        'loaded_m1_sha256':fingerprint_loaded_m1(m1),'original_zip_sha256':ORIGINAL,
        'canonical_run_fast_parity':parity,
        'elapsed_seconds':round(time.perf_counter()-started,2),
        'warning':'Exposed historical design; correlated variants, not OOS or independent hypotheses'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return table,summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--gold-zip',required=True,type=Path)
    p.add_argument('--year',required=True,type=int)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--limit',type=int,default=TOTAL)
    args=p.parse_args()
    if sha256_file(args.gold_zip)!=ORIGINAL:
        raise ValueError('Original private ZIP SHA256 mismatch')
    m1=load_market(args.gold_zip,f'{args.year}-01-01',f'{args.year}-12-31')
    print(json.dumps(run_batch(m1,args.year,args.out,args.limit)[1],indent=2))

if __name__=='__main__':
    main()
