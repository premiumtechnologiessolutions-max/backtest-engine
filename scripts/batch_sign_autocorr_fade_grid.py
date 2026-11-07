"""FAC015 frozen M15 lag-one sign autocorrelation fade; exposed historical design.

Preregistration: 55ca1fd024dc691ec9fc98b2ba82fb5241a0c162.
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
from scripts.batch_compression_h1_grid import local_session_masks, replay_normalized

WINDOWS=(8,12,16,24,32)
CORR_UPPER=(-.4,-.2,0.,.2)
BODY_MIN=(.5,1.,1.5)
REGIMES=('CALM','ACTIVE')
SESSIONS=('ALL','LONDON_LOCAL_08_12','NY_LOCAL_0930_1330')
MULTS=tuple(.5+.25*i for i in range(10))
TOTAL=len(WINDOWS)*len(CORR_UPPER)*len(BODY_MIN)*len(REGIMES)*len(SESSIONS)*len(MULTS)**2
PREREG='55ca1fd024dc691ec9fc98b2ba82fb5241a0c162'
SPEC={'research_id':'NRF-FAC-015','preregistration_commit':PREREG,
      'windows':list(WINDOWS),'corr_upper':list(CORR_UPPER),'body_min':list(BODY_MIN),
      'h1_regimes':list(REGIMES),'sessions':list(SESSIONS),
      'stop_mults':list(MULTS),'target_mults':list(MULTS),'specs_per_year':TOTAL,
      'years':[2012,2013],'original_source_sha256':ORIGINAL,
      'roundtrip_all_in_usd_oz':.4,'historically_exposed_not_oos':True,
      'acceptance':{'min_trades_each_year':100,'min_positive_months_of_24':18,
                    'annual_net_positive_both':True,'worst_month_min':-20.,
                    'annual_floating_dd_max':100.}}

def raw_fade_signals(m15,window,corr_upper,body_min):
    """Only contiguous completed M15; Pearson lag-one sign autocorrelation."""
    if window not in WINDOWS or corr_upper not in CORR_UPPER or body_min not in BODY_MIN:
        raise ValueError('Nonfrozen FAC015 parameter')
    n=len(m15)
    if n<max(window,21):
        return np.empty(0,np.int64),np.empty(0,np.int8),np.empty(0,float)
    op=m15.o.to_numpy(float);close=m15.c.to_numpy(float)
    high=m15.h.to_numpy(float);low=m15.l.to_numpy(float)
    body=close-op;sign=np.sign(body)
    nonzero=pd.Series((sign!=0).astype(int)).rolling(window,min_periods=window).sum().to_numpy()==window
    series=pd.Series(sign);prev=series.shift(1);count=window-1
    sx=prev.rolling(count,min_periods=count).sum().to_numpy()
    sy=series.rolling(count,min_periods=count).sum().to_numpy()
    sxy=(series*prev).rolling(count,min_periods=count).sum().to_numpy()
    varx=count-sx*sx/count;vary=count-sy*sy/count
    corr=np.full(n,np.nan)
    ok=(varx>1e-12)&(vary>1e-12)
    corr[ok]=(sxy[ok]-sx[ok]*sy[ok]/count)/np.sqrt(varx[ok]*vary[ok])
    pb=pd.Series(np.abs(body)).shift(1).rolling(20,min_periods=20).median().to_numpy()
    pr=pd.Series(high-low).shift(1).rolling(20,min_periods=20).median().to_numpy()
    segment=np.cumsum(np.r_[True,np.diff(m15.index.asi8)!=900_000_000_000])
    idx=np.arange(n);back=max(window-1,20)
    valid=(idx>=back)&(segment==segment[np.maximum(0,idx-back)])
    valid &= nonzero & np.isfinite(corr)&(corr<=corr_upper)
    valid &= np.isfinite(pb)&(pb>0)&np.isfinite(pr)&(pr>0)
    valid &= np.abs(body)>=body_min*pb
    selected=np.flatnonzero(valid)
    stamps=np.asarray(m15.close_at.array.asi8//1_000_000_000,dtype=np.int64)
    return stamps[selected],(-sign[selected]).astype(np.int8),pr[selected]

def completed_h1_range_ratio(h1):
    """Last completed H1 range / previous24 observed H1 median within 168h."""
    if h1.empty:return np.empty(0,np.int64),np.empty(0,float)
    stamps=np.asarray(h1.close_at.array.asi8//1_000_000_000,dtype=np.int64)
    ranges=(h1.h-h1.l).to_numpy(float)
    prev=pd.Series(ranges).shift(1).rolling(24,min_periods=24).median().to_numpy()
    idx=np.arange(len(h1))
    valid=(idx>=24)&(stamps-stamps[np.maximum(0,idx-24)]<=168*3600)
    valid &= np.isfinite(prev)&(prev>0)&np.isfinite(ranges)&(ranges>0)
    ratio=np.full(len(h1),np.nan);ratio[valid]=ranges[valid]/prev[valid]
    return stamps,ratio

def causal_h1_session_gate(times,sides,base,h1times,h1ratio,regime,session,masks=None):
    if regime not in REGIMES or session not in SESSIONS:raise ValueError('Nonfrozen FAC015 gate')
    if len(times)!=len(sides) or len(times)!=len(base):raise ValueError('Mismatched signals')
    if not len(times) or not len(h1times):return times[:0],sides[:0],base[:0]
    pos=np.searchsorted(h1times,times,side='right')-1
    safe=np.maximum(pos,0);age=times-h1times[safe]
    valid=(pos>=0)&(age>=0)&(age<=3600)&np.isfinite(h1ratio[safe])
    if regime=='CALM':valid &= h1ratio[safe]<=1.
    else:valid &= h1ratio[safe]>1.
    if masks is None:masks=local_session_masks(times)
    valid &= masks[session]
    return times[valid],sides[valid],base[valid]

def canonical_signals(times,sides,base,sm,tm):
    return [Signal(pd.Timestamp(int(t),unit='s',tz='UTC'),int(side),
                   float(v*sm),float(v*tm),'FAC015_SIGN_AUTOCORR_FADE')
            for t,side,v in zip(times,sides,base)]

def run_batch(m1,year,out,limit=TOTAL):
    if type(year) is not int or year not in (2012,2013) or type(limit) is not int or not 1<=limit<=TOTAL:
        raise ValueError('Outside frozen FAC015 grid')
    if limit>100 and not HAS_JIT:raise RuntimeError('Numba required for bulk')
    out=Path(out)
    if (out/'summary.json').exists():raise FileExistsError('Refuse completed experiment overwrite')
    out.mkdir(parents=True,exist_ok=True)
    frozen=out/'frozen_spec.json'
    if frozen.exists() and json.loads(frozen.read_text())!=SPEC:raise ValueError('Conflicting spec')
    frozen.write_text(json.dumps(SPEC,indent=2),encoding='utf-8')
    start=time.perf_counter()
    m15=aggregate_bars(m1,'M15');h1=aggregate_bars(m1,'H1')
    ht,ratio=completed_h1_range_ratio(h1)
    stamps=np.asarray(m1.index.asi8//1_000_000_000,dtype=np.int64)
    op,hi,lo,cl=(m1[k].to_numpy(float) for k in ('o','h','l','c'))
    months=(m1.index.month.to_numpy(np.int16)-1).astype(np.int8)
    rows=[];cache={};hashes=set()
    for window,corr,body in itertools.product(WINDOWS,CORR_UPPER,BODY_MIN):
        times,sides,base=raw_fade_signals(m15,window,corr,body)
        masks=local_session_masks(times)
        for regime,session in itertools.product(REGIMES,SESSIONS):
            st,sd,sb=causal_h1_session_gate(times,sides,base,ht,ratio,regime,session,masks)
            key=(window,corr,body,regime,session)
            cache[key]=(st,sd,sb)
            hashes.add(hashlib.sha256(st.tobytes()+sd.tobytes()+sb.tobytes()).hexdigest())
            for stop,target in itertools.product(MULTS,MULTS):
                if len(rows)>=limit:break
                monthly,n,net,fees,dd,expired=replay_normalized(
                    stamps,op,hi,lo,cl,months,st,sd,sb,float(stop),float(target))
                ident=f'SAC15_N{window:02d}_C{corr:+.2f}_B{body:.2f}_{regime}_{session}_SL{stop:.2f}_TP{target:.2f}'
                rows.append((ident,window,corr,body,regime,session,stop,target,len(st),expired,
                             n,net,fees,dd,int((monthly>0).sum()),float(monthly.min()),*monthly.tolist()))
            if len(rows)>=limit:break
        if len(rows)>=limit:break
    cols=['id','window','corr_upper','body_min','regime','session','stop_mult','target_mult','signals',
          'expired','trades','net_usd_oz','fees_usd','max_m1_dd','positive_months','worst_month']+[
              f'm{i:02d}' for i in range(1,13)]
    table=pd.DataFrame(rows,columns=cols)
    if not table.id.is_unique:raise AssertionError('Duplicate parameter IDs')
    if not np.allclose(table.net_usd_oz,table[[f'm{i:02d}' for i in range(1,13)]].sum(axis=1),atol=1e-7):raise AssertionError('Monthly reconciliation failed')
    if not np.allclose(table.fees_usd,.4*table.trades,atol=1e-7):raise AssertionError('Fee reconciliation failed')
    ranked=table.sort_values(['positive_months','worst_month','net_usd_oz'],ascending=[False,False,False])
    picks=sorted(set([0,len(table)//2,len(table)-1,int(ranked.index[0])]))
    parity=[]
    for ix in picks:
        row=table.iloc[ix]
        st,sd,sb=cache[(int(row.window),float(row.corr_upper),float(row.body_min),row.regime,row.session)]
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
