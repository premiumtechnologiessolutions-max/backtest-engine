"""Independent slow M1 state-machine audit of frozen FAC014 local event-driven replay.
No private quotes or trade timestamps are written to public GitHub.
"""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from scripts import batch_prior_day_reclaim_grid as f


def independent_slow(m1,times,sides,vols,sm,tm):
    stamps=np.asarray(m1.index.asi8//1_000_000_000,dtype=np.int64)
    op,hi,lo,cl=(m1[k].to_numpy(float) for k in ('o','h','l','c'))
    months=np.asarray(m1.index.month-1,dtype=np.int8)
    n=len(stamps);pointer=0;expired=0;realized=0.;fees=0.;trades=0
    equity=np.zeros(n,float);monthly=np.zeros(12,float)
    pos=None
    for i,now in enumerate(stamps):
        occupied=pos is not None
        if pos is not None:
            side,entry,stop,target=pos
            if (side==1 and op[i]<=stop) or (side==-1 and op[i]>=stop):
                price=op[i];pos=None
            elif (side==1 and op[i]>=target) or (side==-1 and op[i]<=target):
                price=target;pos=None
            else:price=None
            if price is not None:
                pnl=side*(price-entry)-.4
                realized+=pnl;monthly[months[i]]+=pnl;fees+=.4;trades+=1
        while pointer<len(times) and now-times[pointer]>60:
            pointer+=1;expired+=1
        if not occupied and pos is None and pointer<len(times) and now>=times[pointer]:
            side=int(sides[pointer]);entry=op[i]
            pos=(side,entry,entry-side*vols[pointer]*sm,entry+side*vols[pointer]*tm)
            pointer+=1
        if pos is not None:
            side,entry,stop,target=pos
            stophit=lo[i]<=stop if side==1 else hi[i]>=stop
            targethit=hi[i]>=target if side==1 else lo[i]<=target
            if stophit or targethit:
                price=stop if stophit else target
                pnl=side*(price-entry)-.4
                realized+=pnl;monthly[months[i]]+=pnl;fees+=.4;trades+=1
                pos=None
        floating=0. if pos is None else pos[0]*(cl[i]-pos[1])-.4
        equity[i]=realized+floating
    if pos is not None:
        side,entry,_,_=pos
        pnl=side*(cl[-1]-entry)-.4
        realized+=pnl;monthly[months[-1]]+=pnl;fees+=.4;trades+=1
        equity[-1]=realized
    peak=np.maximum.accumulate(np.r_[0.,equity])[1:]
    dd=float(np.max(peak-equity))
    return monthly,trades,realized,fees,dd,expired,equity


def audit(m1,table):
    m15=f.aggregate(m1,15);h1=f.aggregate(m1,60)
    md,up,low=f.prior_utc_day_reference(m1,m15)
    base,valid=f.m15_baseline(m15)
    ht,trend,ratio=f.h1_context(h1)
    stamps=np.asarray(m1.index.asi8//1_000_000_000,dtype=np.int64)
    op,hi,lo,cl=(m1[k].to_numpy(float) for k in ('o','h','l','c'))
    months=np.asarray(m1.index.month-1,dtype=np.int8)
    ranked=table.sort_values(['positive_months','worst_month','net_usd_oz'],ascending=[False,False,False])
    picks=sorted(set((0,len(table)//2,len(table)-1,int(ranked.index[0]))))
    reports=[]
    for ix in picks:
        row=table.iloc[ix]
        t,s,v=f.delayed_reclaims(m15,md,up,low,base,valid,float(row.buffer),int(row.window))
        t,s,v=f.gate(t,s,v,ht,trend,ratio,row.direction,row.h1_mode,row.regime,row.session,f.sessions_masks(t))
        fast=f.replay(stamps,op,hi,lo,cl,months,t,s,v,float(row.stop_mult),float(row.target_mult))
        slow=independent_slow(m1,t,s,v,float(row.stop_mult),float(row.target_mult))
        expected=row[[f'm{i:02d}' for i in range(1,13)]].to_numpy(float)
        monthly_error=max(float(np.max(np.abs(fast[0]-expected))),float(np.max(np.abs(slow[0]-expected))))
        trade_error=abs(int(fast[1])-int(slow[1]))+abs(int(fast[1])-int(row.trades))
        net_error=max(abs(float(fast[2])-float(slow[2])),abs(float(fast[2])-float(row.net_usd_oz)))
        fee_error=max(abs(float(fast[3])-float(slow[3])),abs(float(fast[3])-float(row.fees_usd)))
        dd_error=max(abs(float(fast[4])-float(slow[4])),abs(float(fast[4])-float(row.max_m1_dd)))
        expired_error=abs(int(fast[5])-int(slow[5]))
        if max(monthly_error,trade_error,net_error,fee_error,dd_error,expired_error)>1e-7:
            raise AssertionError(f'{row.id}: {monthly_error,trade_error,net_error,fee_error,dd_error,expired_error}')
        reports.append({'id':row.id,'trades':int(row.trades),'observed_m1_marks':len(slow[-1]),
            'monthly_max_error':monthly_error,'net_error':net_error,'fee_error':fee_error,
            'floating_dd_error':dd_error,'expired_signal_error':expired_error,
            'audit':'INDEPENDENT_LOCAL_SLOW_M1_VS_FAST_NOT_OFFICIAL_CANONICAL'})
    return reports


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--gold-zip',type=Path,required=True);p.add_argument('--year',type=int,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();m1=f.load_year(a.gold_zip,a.year)
    table=pd.read_csv(a.out/'all_candidates_monthly.csv')
    report=audit(m1,table)
    (a.out/'independent_slow_m1_parity.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()