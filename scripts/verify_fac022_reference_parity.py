"""FAC022 local-only full-year slow reference vs fast M1 ledger/equity parity.

Reads PRIVATE Gold ZIP locally. Never upload private fills, quotes or equity ledgers.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
import numpy as np
from norisk_quant.data import load_market,sha256_file
from norisk_quant.execution import run as run_reference
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from scripts import batch_m5_path_efficiency_grid as f

def audit(zip_path,year,identifier,annual_csv):
    if sha256_file(zip_path)!=f.ORIGINAL:raise ValueError('Original ZIP mismatch')
    m1=load_market(zip_path,f'{year}-01-01',f'{year}-12-31')
    cache=f.signal_streams(m1)
    table=pd.read_csv(annual_csv).set_index('id')
    row=table.loc[identifier]
    t,s,b=cache[row.rule_id]
    signals=f.canonical_signals(t,s,b,float(row.stop_mult),float(row.target_mult))
    settings=Settings(ounces=1.,roundtrip_cost_per_ounce=.4)
    ref=run_reference(m1,signals,settings)
    fast=run_fast(m1,signals,settings)
    pd.testing.assert_frame_equal(ref.trades,fast.trades,check_dtype=False,
                                  check_exact=False,atol=1e-9,rtol=0,check_freq=False)
    pd.testing.assert_frame_equal(ref.equity,fast.equity,check_dtype=False,
                                  check_exact=False,atol=1e-9,rtol=0,check_freq=False)
    if ref.expired_signals!=fast.expired_signals:raise AssertionError('Expired mismatch')
    mc=[f'm{i:02d}' for i in range(1,13)]
    monthly=np.bincount(pd.to_datetime(ref.trades.closed_at,utc=True).dt.month,
                        weights=ref.trades.net_pnl.to_numpy(float),minlength=13)[1:]
    if not np.allclose(monthly,row[mc].to_numpy(float),atol=1e-7):
        raise AssertionError('Monthly mismatch')
    if len(ref.trades)!=row.trades or abs(ref.trades.net_pnl.sum()-row.net_usd_oz)>1e-7:
        raise AssertionError('Trades/net mismatch')
    if abs(ref.trades.cost.sum()-row.fees_usd)>1e-7:raise AssertionError('Fee mismatch')
    eq=ref.equity.equity
    dd=float((eq.cummax().clip(lower=0)-eq).clip(lower=0).max())
    if abs(dd-row.max_m1_dd)>1e-7:raise AssertionError('Floating DD mismatch')
    return {'year':year,'status':'PASSED','id':identifier,'trades':len(ref.trades),
            'observed_m1_equity_marks':len(ref.equity),'trade_fields_checked':list(ref.trades.columns),
            'monthly_max_abs_error':float(np.max(np.abs(monthly-row[mc].to_numpy(float)))),
            'max_m1_equity_abs_error':float(np.max(np.abs(ref.equity.equity-fast.equity.equity))),
            'source_sha256':f.ORIGINAL,'independent_reference_vs_fast':True,
            'note':'Synthetic BID M1 OHLC fill model parity, NOT tick BID/ASK or OOS.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gold-zip',type=Path,required=True)
    p.add_argument('--year',type=int,choices=(2012,2013),required=True)
    p.add_argument('--annual-csv',type=Path,required=True)
    p.add_argument('--id',required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    result=audit(a.gold_zip,a.year,a.id,a.annual_csv)
    if a.out.exists():raise FileExistsError('Refuse overwrite of parity evidence')
    a.out.write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ('year','status','trades','observed_m1_equity_marks')},indent=2))
if __name__=='__main__':main()
