"""Independent slow per-observed-M1 parity audit for FAC015P shared portfolio.

Local private-data verification only; emit aggregate differences, never raw quotes.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from norisk_quant.data import load_market,sha256_file
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from scripts.run_fac015p_shared_portfolio import signals_for_year
from scripts.batch_sign_autocorr_fade_grid import ORIGINAL

def independent_shared(m1,signals):
    stamps=np.asarray(m1.index.asi8//1_000_000_000,dtype=np.int64)
    op,hi,lo,cl=(m1[k].to_numpy(float) for k in ('o','h','l','c'))
    months=np.asarray(m1.index.month-1,dtype=np.int8)
    ordered=sorted(signals,key=lambda x:x.confirmed_at)
    times=np.array([int(x.confirmed_at.timestamp()) for x in ordered],dtype=np.int64)
    pointer=0;expired=0;realized=0.;fills=0;fees=0.;pos=None
    monthly=np.zeros(12,float);equity=np.empty(len(stamps),float)
    for i,now in enumerate(stamps):
        occupied=pos is not None
        if pos is not None:
            side,entry,stop,target=pos
            price=None
            if (side==1 and op[i]<=stop) or (side==-1 and op[i]>=stop):price=op[i]
            elif (side==1 and op[i]>=target) or (side==-1 and op[i]<=target):price=target
            if price is not None:
                pnl=side*(price-entry)-.4
                realized+=pnl;monthly[months[i]]+=pnl;fees+=.4;fills+=1;pos=None
        while pointer<len(times) and now-times[pointer]>60:
            pointer+=1;expired+=1
        if not occupied and pos is None and pointer<len(times) and now>=times[pointer]:
            item=ordered[pointer];pointer+=1
            side=item.side;entry=op[i]
            pos=(side,entry,entry-side*item.stop_distance,entry+side*item.target_distance)
        if pos is not None:
            side,entry,stop,target=pos
            hitstop=(lo[i]<=stop) if side==1 else (hi[i]>=stop)
            hittarget=(hi[i]>=target) if side==1 else (lo[i]<=target)
            if hitstop or hittarget:
                price=stop if hitstop else target
                pnl=side*(price-entry)-.4
                realized+=pnl;monthly[months[i]]+=pnl;fees+=.4;fills+=1;pos=None
        equity[i]=realized+(0. if pos is None else pos[0]*(cl[i]-pos[1])-.4)
    if pos is not None:
        side,entry,_,_=pos
        pnl=side*(cl[-1]-entry)-.4
        realized+=pnl;monthly[months[-1]]+=pnl;fees+=.4;fills+=1;equity[-1]=realized
    return monthly,realized,fills,fees,expired,equity

def audit(gold_zip):
    if sha256_file(gold_zip)!=ORIGINAL:raise ValueError('Original ZIP mismatch')
    reports=[]
    for year in (2012,2013):
        m1=load_market(gold_zip,f'{year}-01-01',f'{year}-12-31')
        _,_,signals=signals_for_year(m1)
        fast=run_fast(m1,signals,Settings(ounces=1.,roundtrip_cost_per_ounce=.4))
        slow=independent_shared(m1,signals)
        booked=np.bincount(pd.to_datetime(fast.trades.closed_at,utc=True).dt.month,
                           weights=fast.trades.net_pnl,minlength=13)[1:]
        max_mark=float(np.max(np.abs(fast.equity.equity.to_numpy()-slow[-1])))
        max_month=float(np.max(np.abs(booked-slow[0])))
        if (max_mark>1e-8 or max_month>1e-8 or len(fast.trades)!=slow[2]
            or abs(float(fast.trades.cost.sum())-slow[3])>1e-8):
            raise AssertionError('Shared portfolio slow M1 mismatch')
        reports.append({'year':year,'observed_m1_equity_marks':len(m1),
                        'shared_fills':slow[2],'max_m1_equity_difference':max_mark,
                        'max_monthly_difference':max_month,'expired_signals':slow[4]})
    return reports

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gold-zip',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():raise FileExistsError('Refuse overwrite')
    result=audit(args.gold_zip)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
