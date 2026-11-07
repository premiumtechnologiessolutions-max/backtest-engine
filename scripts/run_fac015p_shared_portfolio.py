"""FAC015P frozen *posthoc* two-component shared-capacity negative control.

Never add separately backtested P/L; execute both frozen signal streams through
one canonical one-position account. 2012/2013 exposed; no OOS/live claim.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from norisk_quant.data import load_market,sha256_file
from norisk_quant.strategy import aggregate_bars
from norisk_quant.model import Signal,Settings
from norisk_quant.fast_engine import run_fast
from scripts import batch_sign_autocorr_fade_grid as f15
from scripts import batch_prior_day_reclaim_grid as f14

def signals_for_year(m1):
    m15=aggregate_bars(m1,'M15');h1=aggregate_bars(m1,'H1')
    t,s,v=f15.raw_fade_signals(m15,12,0.,1.5)
    ht,ratio=f15.completed_h1_range_ratio(h1)
    t,s,v=f15.causal_h1_session_gate(t,s,v,ht,ratio,'CALM',
                                      'NY_LOCAL_0930_1330',f15.local_session_masks(t))
    sig15=f15.canonical_signals(t,s,v,1.5,2.25)
    m15b=f14.aggregate(m1,15);h1b=f14.aggregate(m1,60)
    md,upper,lower=f14.prior_utc_day_reference(m1,m15b)
    base,valid=f14.m15_baseline(m15b)
    bt,bs,bv=f14.delayed_reclaims(m15b,md,upper,lower,base,valid,0.,4)
    ht,trend,ratio=f14.h1_context(h1b)
    bt,bs,bv=f14.gate(bt,bs,bv,ht,trend,ratio,
                      'FOLLOW','ALIGNED','HOT','ALL',f14.sessions_masks(bt))
    sig14=[Signal(pd.Timestamp(int(t),unit='s',tz='UTC'),int(s),
                  float(v*1.25),float(v*1.),
                  'FAC014_PDR_REJECTED') for t,s,v in zip(bt,bs,bv)]
    # Stable sort preserves FAC015 priority for exact simultaneous confirmations.
    return sig15,sig14,sorted(sig15+sig14,key=lambda x:x.confirmed_at)

def summarize(result,year,submitted):
    trades=result.trades
    monthly=np.bincount(pd.to_datetime(trades.closed_at,utc=True).dt.month,
                        weights=trades.net_pnl,minlength=13)[1:]
    equity=result.equity.equity
    dd=float((equity.cummax().clip(lower=0)-equity).clip(lower=0).max())
    if abs(float(monthly.sum())-float(trades.net_pnl.sum()))>1e-7:
        raise AssertionError('Monthly accounting mismatch')
    if abs(float(trades.cost.sum())-.4*len(trades))>1e-7:
        raise AssertionError('Fee accounting mismatch')
    return {'year':year,'signals_submitted':submitted,'filled_trades':len(trades),
            'expired_signals_capacity_or_gap':int(result.expired_signals),
            'net_usd_oz':float(trades.net_pnl.sum()),
            'fees_usd_oz':float(trades.cost.sum()),
            'positive_months':int((monthly>0).sum()),
            'worst_month_usd_oz':float(monthly.min()),
            'max_observed_m1_floating_dd_usd_oz':dd,
            'monthly_utc_exit_net_usd_oz':[float(x) for x in monthly]}

def run_diagnostic(gold_zip:Path):
    if sha256_file(gold_zip)!=f15.ORIGINAL or f15.ORIGINAL!=f14.SOURCE_SHA:
        raise ValueError('Original private source ZIP hash mismatch')
    output={'study':'FAC015P','status':'POSTHOC_EXPOSED_NEGATIVE_CONTROL_NOT_OOS',
            'one_position_shared_capacity':True,'fee_usd_oz':.4,'years':[]}
    for year in (2012,2013):
        m1=load_market(gold_zip,f'{year}-01-01',f'{year}-12-31')
        sig15,sig14,merged=signals_for_year(m1)
        settings=Settings(ounces=1.,roundtrip_cost_per_ounce=.4)
        shared=run_fast(m1,merged,settings)
        solo15=run_fast(m1,sig15,settings)
        solo14=run_fast(m1,sig14,settings)
        output['years'].append({
            'year':year,'shared':summarize(shared,year,len(merged)),
            'standalone_fac015_NOT_ADDITIVE':summarize(solo15,year,len(sig15)),
            'standalone_fac014_NOT_ADDITIVE':summarize(solo14,year,len(sig14)),
            'shared_trades_by_strategy':shared.trades.strategy.value_counts().to_dict()})
    monthly=np.array([y['shared']['monthly_utc_exit_net_usd_oz'] for y in output['years']])
    output['shared_combined']={
        'positive_months_of_24':int((monthly>0).sum()),
        'net_usd_oz':float(monthly.sum()),
        'worst_month_usd_oz':float(monthly.min()),
        'filled_trades':sum(y['shared']['filled_trades'] for y in output['years']),
        'fees_usd_oz':sum(y['shared']['fees_usd_oz'] for y in output['years']),
        'max_annual_floating_dd_usd_oz':max(
            y['shared']['max_observed_m1_floating_dd_usd_oz'] for y in output['years'])}
    return output

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gold-zip',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    out=args.out
    if out.exists():raise FileExistsError('Refuse to overwrite prior audit')
    result=run_diagnostic(args.gold_zip)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result['shared_combined'],indent=2))

if __name__=='__main__':main()
