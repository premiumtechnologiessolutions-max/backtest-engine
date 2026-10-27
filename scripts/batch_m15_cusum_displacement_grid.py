"""FAC021 frozen causal M15 signed CUSUM with completed H1 regime; exposed 2012/13."""
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
from scripts.batch_donchian_grid import HAS_JIT, ORIGINAL
from scripts.batch_compression_h1_grid import local_session_masks, replay_normalized
from scripts.batch_sign_autocorr_fade_grid import completed_h1_range_ratio

THRESHOLDS=(1.5,2.5,3.5)
MODES=('FOLLOW','FADE')
REGIMES=('CALM','ACTIVE')
SESSIONS=('ALL','LONDON_LOCAL_08_12','NY_LOCAL_0930_1330')
MULTS=(.50,.75,1.,1.25,1.50,1.75,2.,2.25)
RULES=len(THRESHOLDS)*len(MODES)*len(REGIMES)*len(SESSIONS)
TOTAL=RULES*len(MULTS)**2
PREREG='fb4e007f08547e078801a52bbfaf13a755205f23'
SPEC={'research_id':'NRF-FAC-021','preregistration_commit':PREREG,
      'family':'completed M15 path-dependent signed CUSUM with H1 volatility halt',
      'thresholds':list(THRESHOLDS),'modes':list(MODES),'regimes':list(REGIMES),
      'sessions':list(SESSIONS),'stop_mults':list(MULTS),'target_mults':list(MULTS),
      'signal_rule_groups_per_year':RULES,'specs_per_year':TOTAL,'years':[2012,2013],
      'source_sha256':ORIGINAL,'roundtrip_all_in_usd_oz':.4,
      'historically_exposed_not_oos':True,
      'acceptance':{'min_fills_each_year':100,'min_positive_months_of_24':18,
                    'annual_net_positive_both':True,'worst_month_min':-20.,
                    'annual_floating_dd_max_each_year':100.}}

def _ns(index):
    return index.as_unit('ns').asi8

def cusum_events(m15,threshold):
    """One event at completed M15 close; previous-20 range normalization; gap reset."""
    if type(threshold) not in (int,float) or threshold not in THRESHOLDS:
        raise ValueError('Nonfrozen FAC021 threshold')
    empty=(np.empty(0,np.int64),np.empty(0,np.int8),np.empty(0,float))
    if len(m15)<22:return empty
    if (not isinstance(m15.index,pd.DatetimeIndex) or m15.index.tz is None or
        str(m15.index.tz)!='UTC' or not m15.index.is_monotonic_increasing or
        not m15.index.is_unique or 'close_at' not in m15 or
        not np.array_equal(_ns(pd.DatetimeIndex(m15.close_at)),_ns(m15.index)+900_000_000_000)):
        raise ValueError('Requires unique ordered complete UTC M15 bars with close_at')
    idx=_ns(m15.index)
    closes=m15.c.to_numpy(float)
    ranges=(m15.h-m15.l).to_numpy(float)
    baseline=pd.Series(ranges).shift(1).rolling(20,min_periods=20).median().to_numpy()
    stamps=(_ns(pd.DatetimeIndex(m15.close_at))//1_000_000_000).astype(np.int64)
    events=[];sides=[];bases=[]
    pos=0.;neg=0.;run=0
    for j in range(1,len(m15)):
        if idx[j]-idx[j-1]!=900_000_000_000:
            run=0;pos=0.;neg=0.
        else:
            run+=1
        if run<20 or not np.isfinite(baseline[j]) or baseline[j]<=0 or not np.isfinite(closes[j]) or not np.isfinite(closes[j-1]):
            pos=0.;neg=0.;continue
        z=(closes[j]-closes[j-1])/baseline[j]
        if not np.isfinite(z):pos=0.;neg=0.;continue
        pos=max(0.,pos+z);neg=min(0.,neg+z)
        side=1 if pos>=threshold else (-1 if neg<=-threshold else 0)
        if side:
            events.append(int(stamps[j]));sides.append(side);bases.append(float(baseline[j]))
            pos=0.;neg=0.
    return np.asarray(events,np.int64),np.asarray(sides,np.int8),np.asarray(bases,float)

def h1_gate(times,sides,base,h1times,h1ratio,regime,session,masks=None):
    """Last completed H1 at most 3600s old, H1 range ratio <=2 volatility halt."""
    if regime not in REGIMES or session not in SESSIONS:raise ValueError('Nonfrozen gate')
    if len(times)!=len(sides) or len(times)!=len(base) or len(h1times)!=len(h1ratio):
        raise ValueError('Mismatched signal/context arrays')
    if not len(times) or not len(h1times):return times[:0],sides[:0],base[:0]
    if np.any(np.diff(times)<0) or np.any(np.diff(h1times)<=0) or np.any(~np.isin(sides,[-1,1])):
        raise ValueError('Invalid signal chronology or side')
    last=np.searchsorted(h1times,times,side='right')-1
    safe=np.maximum(0,last);age=times-h1times[safe]
    valid=(last>=0)&(age>=0)&(age<=3600)&np.isfinite(h1ratio[safe])
    valid &= (h1ratio[safe]>0)&(h1ratio[safe]<=2.)
    valid &= (h1ratio[safe]<=1.) if regime=='CALM' else (h1ratio[safe]>1.)
    if masks is None:masks=local_session_masks(times)
    valid &= masks[session]
    return times[valid],sides[valid],base[valid]

def rule_id(threshold,mode,regime,session):
    return f'CUSUM15_K{threshold:.2f}_{mode}_{regime}_{session}'

def signal_streams(m1):
    m15=aggregate_bars(m1,'M15');h1=aggregate_bars(m1,'H1')
    ht,hr=completed_h1_range_ratio(h1);cache={}
    for threshold in THRESHOLDS:
        times,sides,base=cusum_events(m15,threshold)
        masks=local_session_masks(times)
        for mode,regime,session in itertools.product(MODES,REGIMES,SESSIONS):
            sign=sides if mode=='FOLLOW' else -sides
            key=rule_id(threshold,mode,regime,session)
            cache[key]=h1_gate(times,sign,base,ht,hr,regime,session,masks)
    if len(cache)!=RULES:raise AssertionError('Duplicate/missing frozen rules')
    return cache

def preflight(m1,year,out):
    if type(year) is not int or year not in (2012,2013):
        raise ValueError('Outside frozen design years')
    out=Path(out)
    if out.exists():raise FileExistsError('Refuse prior preflight overwrite')
    out.parent.mkdir(parents=True,exist_ok=True)
    counts={k:len(v[0]) for k,v in signal_streams(m1).items()}
    result={'id':'NRF-FAC-020','year':year,'preregistration_commit':PREREG,
            'original_zip_sha256':ORIGINAL,'loaded_m1_sha256':fingerprint_loaded_m1(m1),
            'rule_counts':counts,'max_signals':max(counts.values()),
            'nonzero_rules':sum(n>0 for n in counts.values()),'no_exit_outcomes_examined':True}
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

def joint_preflight(first,second):
    if {first.get('year'),second.get('year')}!={2012,2013}:
        raise ValueError('Requires both frozen years')
    if first.get('preregistration_commit')!=PREREG or second.get('preregistration_commit')!=PREREG:
        raise ValueError('Frozen preregistration mismatch')
    if first.get('original_zip_sha256')!=ORIGINAL or second.get('original_zip_sha256')!=ORIGINAL:
        raise ValueError('Original source mismatch')
    a=first['rule_counts'];b=second['rule_counts']
    if (set(a)!=set(b) or len(a)!=RULES or
        any(type(v) is not int or v<0 for v in list(a.values())+list(b.values()))):
        raise ValueError('Malformed signal-only preflight')
    ids=[k for k in a if a[k]>=100 and b[k]>=100]
    return {'same_id_rules_ge100_each_year':len(ids),'jointly_eligible_rule_ids':ids,
            'decision':'ELIGIBLE_FOR_EXIT_SWEEP' if ids else 'STRUCTURALLY_UNREACHABLE_MIN_FILLS',
            'rule_groups':RULES,'min_fills_each_year':100}

def canonical_signals(times,sides,base,sm,tm):
    return [Signal(pd.Timestamp(int(t),unit='s',tz='UTC'),int(s),
                   float(b*sm),float(b*tm),'FAC021_M15_CUSUM')
            for t,s,b in zip(times,sides,base)]

def run_batch(m1,year,out,limit=TOTAL):
    if type(year) is not int or year not in (2012,2013) or type(limit) is not int or not 1<=limit<=TOTAL:
        raise ValueError('Outside frozen FAC021 grid')
    if limit>100 and not HAS_JIT:raise RuntimeError('Numba required for full exit sweep')
    out=Path(out)
    if out.exists():raise FileExistsError('Refuse experiment overwrite')
    out.mkdir(parents=True,exist_ok=False)
    (out/'frozen_spec.json').write_text(json.dumps(SPEC,indent=2),encoding='utf-8')
    started=time.perf_counter();cache=signal_streams(m1)
    stamps=(_ns(m1.index)//1_000_000_000).astype(np.int64)
    op,hi,lo,cl=(m1[k].to_numpy(float) for k in ('o','h','l','c'))
    months=(m1.index.month.to_numpy(np.int16)-1).astype(np.int8)
    rows=[];hashes=set()
    for q,(t,s,b) in cache.items():
        hashes.add(hashlib.sha256(t.tobytes()+s.tobytes()+b.tobytes()).hexdigest())
        for sm,tm in itertools.product(MULTS,MULTS):
            if len(rows)>=limit:break
            monthly,n,net,fees,dd,expired=replay_normalized(
                stamps,op,hi,lo,cl,months,t,s,b,float(sm),float(tm))
            ident=f'{q}_SL{sm:.2f}_TP{tm:.2f}'
            rows.append((ident,q,sm,tm,len(t),expired,n,net,fees,dd,
                         int((monthly>0).sum()),float(monthly.min()),*monthly.tolist()))
        if len(rows)>=limit:break
    monthcols=[f'm{i:02d}' for i in range(1,13)]
    cols=['id','rule_id','stop_mult','target_mult','signals','expired','trades',
          'net_usd_oz','fees_usd','max_m1_dd','positive_months','worst_month']+monthcols
    table=pd.DataFrame(rows,columns=cols)
    if (not table.id.is_unique or
        not np.allclose(table.net_usd_oz,table[monthcols].sum(axis=1),atol=1e-7) or
        not np.allclose(table.fees_usd,.4*table.trades,atol=1e-7)):
        raise AssertionError('Monthly/fee/ID invariant failed')
    ranked=table.sort_values(['positive_months','worst_month','net_usd_oz'],
                             ascending=[False,False,False])
    picks=sorted(set([0,len(table)//2,len(table)-1,int(ranked.index[0])]))
    parity=[]
    for ix in picks:
        row=table.iloc[ix];t,s,b=cache[row.rule_id]
        ref=run_fast(m1,canonical_signals(t,s,b,row.stop_mult,row.target_mult),
                     Settings(ounces=1.,roundtrip_cost_per_ounce=.4))
        booked=np.bincount(pd.to_datetime(ref.trades.closed_at,utc=True).dt.month,
                           weights=ref.trades.net_pnl.to_numpy(float),minlength=13)[1:]
        eq=ref.equity.equity
        dd=float((eq.cummax().clip(lower=0)-eq).clip(lower=0).max())
        error=float(np.max(np.abs(booked-row[monthcols].to_numpy(float))))
        if (error>1e-7 or abs(dd-row.max_m1_dd)>1e-7 or len(ref.trades)!=row.trades or
            abs(ref.trades.net_pnl.sum()-row.net_usd_oz)>1e-7 or
            abs(ref.trades.cost.sum()-row.fees_usd)>1e-7):
            raise AssertionError(f'FAC021 canonical parity failed: {row.id}')
        parity.append({'id':row.id,'trades':int(row.trades),
                       'monthly_max_error':error,'floating_dd_error':abs(dd-row.max_m1_dd)})
    table.to_csv(out/'all_candidates_monthly.csv',index=False)
    ranked.head(20).to_csv(out/'exploratory_top20_NOT_OOS.csv',index=False)
    summary={'status':'COMPLETED_EXPOSED_DESIGN_NOT_OOS','year':year,
             'executed_annual_replays':len(table),
             'active_annual_replays':int((table.trades>0).sum()),
             'zero_trade_replays':int((table.trades==0).sum()),
             'monthly_values_including_zero':len(table)*12,
             'unique_signal_streams':len(hashes),
             'max_positive_months':int(table.positive_months.max()),
             'positive_12_months':int((table.positive_months==12).sum()),
             'positive_annual_net':int((table.net_usd_oz>0).sum()),
             'canonical_run_fast_parity':parity,'original_zip_sha256':ORIGINAL,
             'loaded_m1_sha256':fingerprint_loaded_m1(m1),
             'elapsed_seconds':round(time.perf_counter()-started,2),
             'warning':'Historically exposed correlated grid; no OOS or broker-tick proof.'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return table,summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold-zip',type=Path,required=True)
    parser.add_argument('--year',type=int,choices=(2012,2013),required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--mode',choices=('preflight','replay'),default='preflight')
    parser.add_argument('--limit',type=int,default=TOTAL)
    args=parser.parse_args()
    if sha256_file(args.gold_zip)!=ORIGINAL:
        raise ValueError('Original private Gold ZIP SHA256 mismatch')
    m1=load_market(args.gold_zip,f'{args.year}-01-01',f'{args.year}-12-31')
    result=(preflight(m1,args.year,args.out) if args.mode=='preflight'
            else run_batch(m1,args.year,args.out,args.limit)[1])
    print(json.dumps({k:v for k,v in result.items() if k!='rule_counts'},indent=2))

if __name__=='__main__':
    main()
