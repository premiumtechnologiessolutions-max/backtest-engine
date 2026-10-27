"""NRF-FAC-014 frozen prior-UTC-day breakout then delayed M15 reclaim.
Preregistered at 15b7083b13b4d434036612b509d189eb742ae339 BEFORE FAC014 outcomes.
Historically exposed 2012/2013 only; private original ZIP never leaves local machine.
"""
from __future__ import annotations
import argparse, hashlib, itertools, json, time, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
try:
    from numba import njit
    HAS_JIT = True
except ImportError:
    HAS_JIT = False
    def njit(*args, **kwargs):
        def wrap(func):
            return func
        return wrap

SOURCE_SHA = '1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121'
PREREG = '15b7083b13b4d434036612b509d189eb742ae339'
BUFFERS = (0., .25, .50)
WINDOWS = (1,2,4,8)
DIRECTIONS = ('FADE','FOLLOW')
H1_MODES = ('ALIGNED','CONTRA','IGNORE')
REGIMES = ('QUIET','HOT')
SESSIONS = ('ALL','LONDON_LOCAL_08_12','NY_LOCAL_0930_1330')
MULTS = (.5,.75,1.,1.25,1.5,1.75,2.,2.5)
TOTAL = len(BUFFERS)*len(WINDOWS)*len(DIRECTIONS)*len(H1_MODES)*len(REGIMES)*len(SESSIONS)*len(MULTS)**2
SPEC = dict(research_id='NRF-FAC-014',preregistration_commit=PREREG,
    buffers=list(BUFFERS),windows=list(WINDOWS),directions=list(DIRECTIONS),
    h1_modes=list(H1_MODES),regimes=list(REGIMES),sessions=list(SESSIONS),
    stop_mults=list(MULTS),target_mults=list(MULTS),specs_per_year=TOTAL,
    years=[2012,2013],source_sha256=SOURCE_SHA,roundtrip_all_in_usd_oz=.4,
    historical_design_not_oos=True)

def load_year(zip_path:Path,year:int):
    if hashlib.sha256(zip_path.read_bytes()).hexdigest()!=SOURCE_SHA:
        raise ValueError('Original source ZIP hash mismatch')
    if year not in (2012,2013):raise ValueError('Frozen design years only')
    with zipfile.ZipFile(zip_path) as z:
        rec=json.loads(z.read(f'{year}.json'))
    frame=pd.DataFrame.from_records(rec)
    if frame.empty or frame.ts.duplicated().any() or not frame.ts.is_monotonic_increasing:
        raise ValueError('Invalid original M1 timestamps')
    if not ((frame.ts.to_numpy(np.int64)%60)==0).all():raise ValueError('Sub-minute M1 timestamps')
    for col in ('o','h','l','c','ao','ah','al','ac'):
        if not np.isfinite(frame[col].to_numpy(float)).all():raise ValueError('Invalid quote')
    idx=pd.to_datetime(frame.ts,unit='s',utc=True)
    frame.index=idx
    if frame.index.year.min()!=year or frame.index.year.max()!=year:raise ValueError('Year leakage')
    return frame

def aggregate(m1,width):
    agg=m1.resample(f'{width}min',label='left',closed='left',origin='epoch')
    bars=agg.agg({'o':'first','h':'max','l':'min','c':'last'})
    bars=bars[agg.c.count()==width].dropna()
    bars['close_at']=bars.index+pd.Timedelta(minutes=width)
    return bars

def prior_utc_day_reference(m1,m15):
    ts=m1.index.asi8//1_000_000_000
    day=ts//86400
    unique,starts,counts=np.unique(day,return_index=True,return_counts=True)
    hi=m1.h.to_numpy(float);lo=m1.l.to_numpy(float)
    dh=np.maximum.reduceat(hi,starts);dl=np.minimum.reduceat(lo,starts)
    max_gap=np.array([int(np.diff(ts[s:s+n]).max()) if n>1 else 10**9 for s,n in zip(starts,counts)])
    eligible=(counts>=1200)&(max_gap<=180*60)
    valid_days=unique[eligible]
    if not len(valid_days):raise ValueError('No complete prior UTC days')
    valid_hi=dh[eligible];valid_lo=dl[eligible]
    mt=(m15.index.asi8//1_000_000_000).astype(np.int64)
    md=mt//86400
    pos=np.searchsorted(valid_days,md,side='left')-1
    safe=np.maximum(pos,0)
    ok=(pos>=0)&(md-valid_days[safe]<=4)&(md>valid_days[safe])
    upper=np.where(ok,valid_hi[safe],np.nan)
    lower=np.where(ok,valid_lo[safe],np.nan)
    return md,upper,lower

def m15_baseline(m15):
    width=900_000_000_000
    seg=np.cumsum(np.r_[True,np.diff(m15.index.asi8)!=width])
    r=(m15.h-m15.l).to_numpy(float)
    base=pd.Series(r).shift(1).rolling(20,min_periods=20).median().to_numpy()
    n=np.arange(len(m15))
    valid=(n>=20)&(seg==seg[np.maximum(n-20,0)])&np.isfinite(base)&(base>0)
    return base,valid

def delayed_reclaims(m15,md,upper,lower,base,valid,k,window):
    if k not in BUFFERS or window not in WINDOWS:raise ValueError('Unfrozen buffer/window')
    c=m15.c.to_numpy(float)
    stamps=np.asarray(m15.close_at.array.asi8//1_000_000_000,dtype=np.int64)
    opens=np.asarray(m15.index.asi8//1_000_000_000,dtype=np.int64)
    out_t=[];out_s=[];out_r=[]
    upper_start=-1;lower_start=-1;upper_used=lower_used=False
    for j in range(len(m15)):
        if j==0 or md[j]!=md[j-1]:
            upper_start=lower_start=-1;upper_used=lower_used=False
        elif opens[j]-opens[j-1]!=900:
            if upper_start>=0:upper_used=True
            if lower_start>=0:lower_used=True
            upper_start=lower_start=-1
        if not valid[j] or not np.isfinite(upper[j]) or not np.isfinite(lower[j]):
            if upper_start>=0:upper_used=True
            if lower_start>=0:lower_used=True
            upper_start=lower_start=-1
            continue
        if upper_start>=0 and j-upper_start>window:upper_used=True;upper_start=-1
        if lower_start>=0 and j-lower_start>window:lower_used=True;lower_start=-1
        inside=(lower[j]<c[j]<upper[j])
        up_reclaim=(upper_start>=0 and j>upper_start and inside)
        low_reclaim=(lower_start>=0 and j>lower_start and inside)
        if up_reclaim or low_reclaim:
            if up_reclaim!=low_reclaim:
                out_t.append(stamps[j]);out_s.append(-1 if up_reclaim else 1);out_r.append(base[j])
            if up_reclaim:upper_start=-1;upper_used=True
            if low_reclaim:lower_start=-1;lower_used=True
        if not upper_used and upper_start<0 and c[j]>upper[j]+k*base[j]:upper_start=j
        if not lower_used and lower_start<0 and c[j]<lower[j]-k*base[j]:lower_start=j
    return np.array(out_t,dtype=np.int64),np.array(out_s,dtype=np.int8),np.array(out_r,dtype=np.float64)

def h1_context(h1):
    times=np.asarray(h1.close_at.array.asi8//1_000_000_000,dtype=np.int64)
    closes=h1.c.to_numpy(float)
    trend=np.sign(pd.Series(closes).ewm(span=8,adjust=False).mean().to_numpy()-pd.Series(closes).ewm(span=24,adjust=False).mean().to_numpy()).astype(np.int8)
    ranges=(h1.h-h1.l).to_numpy(float)
    baseline=pd.Series(ranges).shift(1).rolling(24,min_periods=24).median().to_numpy()
    ratio=ranges/baseline
    idx=np.arange(len(times))
    valid=(idx>=25)&(times-times[np.maximum(0,idx-25)]<=168*3600)&np.isfinite(ratio)&(ratio>0)&(trend!=0)
    ratio[~valid]=np.nan
    return times,trend,ratio

def sessions_masks(times):
    dates=pd.to_datetime(times,unit='s',utc=True)
    london=dates.tz_convert('Europe/London');ny=dates.tz_convert('America/New_York')
    lm=np.asarray(london.hour*60+london.minute);nm=np.asarray(ny.hour*60+ny.minute)
    return {'ALL':np.ones(len(times),dtype=bool),
            'LONDON_LOCAL_08_12':(lm>=480)&(lm<720),
            'NY_LOCAL_0930_1330':(nm>=570)&(nm<810)}

def gate(times,sides,base,h1times,trend,ratio,direction,mode,regime,session,masks):
    if not len(times):return times,sides,base
    pos=np.searchsorted(h1times,times,side='right')-1
    safe=np.maximum(0,pos)
    age=times-h1times[safe]
    s=sides if direction=='FADE' else -sides
    good=(pos>=0)&(age>=0)&(age<=3600)&np.isfinite(ratio[safe])
    good&=(ratio[safe]<=1.) if regime=='QUIET' else (ratio[safe]>1.)
    if mode=='ALIGNED':good&=s==trend[safe]
    elif mode=='CONTRA':good&=s==-trend[safe]
    good&=masks[session]
    return times[good],s[good].astype(np.int8),base[good]

@njit(cache=True)
def replay(stamps,op,hi,lo,cl,months,signalt,signs,vols,sm,tm):
    n=len(stamps);pointer=0;next_free=0;trades=0;expired=0
    monthly=np.zeros(12,np.float64);realized=0.;fees=0.;peak=0.;ddmax=0.
    while next_free<n and pointer<len(signalt):
        confirmed=signalt[pointer]
        at=np.searchsorted(stamps,confirmed)
        if at<next_free:at=next_free
        if at>=n:break
        if stamps[at]-confirmed>60:
            pointer+=1;expired+=1;continue
        side=signs[pointer];sd=vols[pointer]*sm;td=vols[pointer]*tm;pointer+=1
        price=op[at];stop=price-side*sd;target=price+side*td;entry=at;exited=False
        while at<n:
            opening=op[at]
            if at>entry:
                if (side==1 and opening<=stop) or (side==-1 and opening>=stop):
                    exitprice=opening;exited=True
                elif (side==1 and opening>=target) or (side==-1 and opening<=target):
                    exitprice=target;exited=True
            if not exited:
                stophit=(lo[at]<=stop) if side==1 else (hi[at]>=stop)
                targethit=(hi[at]>=target) if side==1 else (lo[at]<=target)
                if stophit:exitprice=stop;exited=True
                elif targethit:exitprice=target;exited=True
            if exited:
                pnl=side*(exitprice-price)-.4
                realized+=pnl;monthly[months[at]]+=pnl;trades+=1;fees+=.4
                if realized>peak:peak=realized
                dd=peak-realized
                if dd>ddmax:ddmax=dd
                next_free=at+1;break
            mark=realized+side*(cl[at]-price)-.4
            if mark>peak:peak=mark
            dd=peak-mark
            if dd>ddmax:ddmax=dd
            at+=1
        if not exited:
            last=n-1;pnl=side*(cl[last]-price)-.4
            realized+=pnl;monthly[months[last]]+=pnl;trades+=1;fees+=.4
            if realized>peak:peak=realized
            dd=peak-realized
            if dd>ddmax:ddmax=dd
            next_free=n
    return monthly,trades,realized,fees,ddmax,expired

def run_batch(m1,year,out,limit=TOTAL):
    if type(year) is not int or year not in (2012,2013) or type(limit) is not int or not 1<=limit<=TOTAL:raise ValueError('Unfrozen scope')
    if limit>100 and not HAS_JIT:raise RuntimeError('Numba required for bulk replay')
    out=Path(out)
    if (out/'summary.json').exists():raise FileExistsError('Completed batch cannot be overwritten')
    out.mkdir(parents=True,exist_ok=True)
    (out/'frozen_spec.json').write_text(json.dumps(SPEC,indent=2))
    start=time.perf_counter()
    m15=aggregate(m1,15);h1=aggregate(m1,60)
    md,upper,lower=prior_utc_day_reference(m1,m15)
    base,valid=m15_baseline(m15)
    ht,trend,ratio=h1_context(h1)
    stamps=np.asarray(m1.index.asi8//1_000_000_000,dtype=np.int64)
    op,hi,lo,cl=(m1[k].to_numpy(float) for k in ('o','h','l','c'))
    months=np.asarray(m1.index.month-1,dtype=np.int8)
    rows=[];streams=set();cache={}
    for k,w in itertools.product(BUFFERS,WINDOWS):
        bt,bs,bv=delayed_reclaims(m15,md,upper,lower,base,valid,k,w)
        masks=sessions_masks(bt)
        for direction,mode,regime,session in itertools.product(DIRECTIONS,H1_MODES,REGIMES,SESSIONS):
            t,s,v=gate(bt,bs,bv,ht,trend,ratio,direction,mode,regime,session,masks)
            cache[(k,w,direction,mode,regime,session)]=(t,s,v)
            streams.add(hashlib.sha256(t.tobytes()+s.tobytes()+v.tobytes()).hexdigest())
            for sm,tm in itertools.product(MULTS,MULTS):
                if len(rows)>=limit:break
                monthly,trades,net,fees,dd,expired=replay(stamps,op,hi,lo,cl,months,t,s,v,sm,tm)
                ident=f'PDR15_K{k:.2f}_W{w}_{direction}_{mode}_{regime}_{session}_SL{sm:.2f}_TP{tm:.2f}'
                rows.append((ident,k,w,direction,mode,regime,session,sm,tm,len(t),expired,trades,net,fees,dd,int((monthly>0).sum()),float(monthly.min()),*monthly.tolist()))
            if len(rows)>=limit:break
        if len(rows)>=limit:break
    cols=['id','buffer','window','direction','h1_mode','regime','session','stop_mult','target_mult','signals','expired','trades','net_usd_oz','fees_usd','max_m1_dd','positive_months','worst_month']+[f'm{i:02d}' for i in range(1,13)]
    table=pd.DataFrame(rows,columns=cols)
    if not table.id.is_unique:raise AssertionError('Duplicate specs')
    if not np.allclose(table.net_usd_oz,table[[f'm{i:02d}' for i in range(1,13)]].sum(axis=1),atol=1e-7):raise AssertionError('Monthly ledger')
    if not np.allclose(table.fees_usd,.4*table.trades,atol=1e-7):raise AssertionError('Fee ledger')
    table.to_csv(out/'all_candidates_monthly.csv',index=False)
    table.sort_values(['positive_months','worst_month','net_usd_oz'],ascending=[False,False,False]).head(20).to_csv(out/'exploratory_top20_NOT_OOS.csv',index=False)
    summary={'status':'LOCAL_COMPLETE_CANONICAL_PARITY_PENDING','year':year,'executed_annual_replays':len(table),
             'active_annual_replays':int((table.trades>0).sum()),'zero_trade_replays':int((table.trades==0).sum()),
             'monthly_values':len(table)*12,'unique_entry_streams':len(streams),
             'positive_annual_net_specs':int((table.net_usd_oz>0).sum()),
             'max_positive_months':int(table.positive_months.max()),'configs_12_of_12':int((table.positive_months==12).sum()),
             'preregistration_commit':PREREG,'source_sha256':SOURCE_SHA,
             'elapsed_seconds':round(time.perf_counter()-start,2),'note':'Exposed design only, no independent OOS or broker tick fills'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    return table,summary,cache

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--gold-zip',type=Path,required=True);p.add_argument('--year',type=int,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--limit',type=int,default=TOTAL)
    a=p.parse_args();m1=load_year(a.gold_zip,a.year)
    print(json.dumps(run_batch(m1,a.year,a.out,a.limit)[1],indent=2))
if __name__=='__main__':main()