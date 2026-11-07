"""FAC017 frozen two-bar M15 volatility shock reversal, gap-aware H1 regime.

Preregistered at e88adcea2f00927e15d93e37d11e8f95e7680911 before outcomes.
2012/2013 are historically exposed design data, never independent OOS.
Private original Gold ZIP is local-only and must pass SHA256 authentication.
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
from scripts.batch_donchian_grid import HAS_JIT, ORIGINAL
from scripts.batch_compression_h1_grid import local_session_masks, replay_normalized
from scripts.batch_sign_autocorr_fade_grid import completed_h1_range_ratio

LOOKBACKS = (12, 20, 32, 48)
SHOCKS = (1.25, 1.5, 2., 2.5)
RETRACES = (.25, .4, .55)
REGIMES = ('QUIET', 'ACTIVE')
SESSIONS = ('ALL', 'LONDON_LOCAL_08_12', 'NY_LOCAL_0930_1330')
MULTS = tuple(.5 + .25*i for i in range(8))
TOTAL = len(LOOKBACKS)*len(SHOCKS)*len(RETRACES)*len(REGIMES)*len(SESSIONS)*len(MULTS)**2
PREREG = 'e88adcea2f00927e15d93e37d11e8f95e7680911'
SPEC = {
    'research_id': 'NRF-FAC-017', 'preregistration_commit': PREREG,
    'family': 'two-bar M15 displacement-shock exhaustion and reversal, gap-aware completed H1 volatility regime',
    'lookbacks': list(LOOKBACKS), 'shocks': list(SHOCKS),
    'retraces': list(RETRACES), 'regimes': list(REGIMES),
    'sessions': list(SESSIONS), 'stop_mults': list(MULTS),
    'target_mults': list(MULTS), 'specs_per_year': TOTAL,
    'years': [2012, 2013], 'source_sha256': ORIGINAL,
    'roundtrip_all_in_usd_oz': .4, 'historically_exposed_not_oos': True,
    'acceptance': {'min_fills_each_year': 100, 'min_positive_months_of_24': 18,
                   'annual_net_positive_both': True, 'worst_month_min': -20.,
                   'annual_floating_dd_max': 100.},
}

def shock_reversal_signals(m15, lookback, shock, retrace):
    """Use shock j-1, baseline through j-2, reversal confirmed only at j close."""
    if (type(lookback) is not int or lookback not in LOOKBACKS or
        type(shock) not in (int, float) or shock not in SHOCKS or
        type(retrace) not in (int, float) or retrace not in RETRACES):
        raise ValueError('Nonfrozen FAC017 shock parameters')
    empty = (np.empty(0, np.int64), np.empty(0, np.int8), np.empty(0, float))
    if len(m15) < max(lookback+2, 22):
        return empty
    if m15.index.tz is None or str(m15.index.tz) != 'UTC':
        raise ValueError('M15 bars must use UTC')
    if (not m15.index.is_monotonic_increasing or
        not m15.index.is_unique or
        not (m15.close_at.array.asi8 == m15.index.asi8 + 900_000_000_000).all()):
        raise ValueError('Invalid M15 completed-bar chronology')
    stamps = np.asarray(m15.close_at.array.asi8//1_000_000_000, dtype=np.int64)
    segment = np.cumsum(np.r_[True, np.diff(m15.index.asi8) != 900_000_000_000])
    op = m15.o.to_numpy(float); hi = m15.h.to_numpy(float)
    lo = m15.l.to_numpy(float); close = m15.c.to_numpy(float)
    ranges = hi-lo
    # At j: shift(2) rolling N uses j-N-1 ... j-2; excludes j-1 shock and j signal.
    shock_base = pd.Series(ranges).shift(2).rolling(lookback, min_periods=lookback).median().to_numpy()
    # At j: previous20 includes j-1 shock, but excludes current j.
    risk_base = pd.Series(ranges).shift(1).rolling(20, min_periods=20).median().to_numpy()
    prev_o = np.r_[np.nan, op[:-1]]
    prev_c = np.r_[np.nan, close[:-1]]
    prev_h = np.r_[np.nan, hi[:-1]]
    prev_l = np.r_[np.nan, lo[:-1]]
    prev_r = np.r_[np.nan, ranges[:-1]]
    idx = np.arange(len(m15))
    back = max(lookback+1, 20)
    valid = (idx >= back) & (segment == segment[np.maximum(0, idx-back)])
    valid &= (np.isfinite(shock_base) & (shock_base > 0) &
              np.isfinite(risk_base) & (risk_base > 0) &
              np.isfinite(prev_r) & (prev_r > 0) &
              np.isfinite(op) & np.isfinite(close) &
              np.isfinite(prev_o) & np.isfinite(prev_c) &
              np.isfinite(prev_h) & np.isfinite(prev_l))
    valid &= prev_r >= shock*shock_base
    bullish = (prev_c > prev_o) & (prev_c >= prev_l+.8*prev_r)
    bearish = (prev_c < prev_o) & (prev_c <= prev_l+.2*prev_r)
    within = (close >= prev_l) & (close <= prev_h)
    short = valid & bullish & (close < op) & within & (close <= prev_h-retrace*prev_r)
    long = valid & bearish & (close > op) & within & (close >= prev_l+retrace*prev_r)
    selected = np.flatnonzero(short | long)
    return stamps[selected], np.where(long[selected], 1, -1).astype(np.int8), risk_base[selected]

def causal_regime_session_gate(times, sides, base, h1times, h1ratio, regime, session, masks=None):
    """Last completed H1 <=1h old; ACTIVE halts when ratio >2.0."""
    if regime not in REGIMES or session not in SESSIONS:
        raise ValueError('Nonfrozen FAC017 regime/session')
    if len(times) != len(sides) or len(times) != len(base) or len(h1times) != len(h1ratio):
        raise ValueError('Mismatched arrays')
    if not len(times) or not len(h1times):
        return times[:0], sides[:0], base[:0]
    if (np.any(np.diff(h1times) <= 0) or np.any(np.diff(times) < 0) or
        np.any(~np.isin(sides, [-1, 1]))):
        raise ValueError('Noncausal timestamps or invalid sides')
    last = np.searchsorted(h1times, times, side='right')-1
    safe = np.maximum(last, 0)
    age = times-h1times[safe]
    valid = (last >= 0) & (age >= 0) & (age <= 3600)
    valid &= np.isfinite(h1ratio[safe]) & (h1ratio[safe] > 0)
    if regime == 'QUIET':
        valid &= h1ratio[safe] <= 1.
    else:
        valid &= (h1ratio[safe] > 1.) & (h1ratio[safe] <= 2.)
    if masks is None:
        masks = local_session_masks(times)
    valid &= masks[session]
    return times[valid], sides[valid], base[valid]

def canonical_signals(times, sides, base, stop_mult, target_mult):
    return [Signal(pd.Timestamp(int(t), unit='s', tz='UTC'), int(s),
                   float(v*stop_mult), float(v*target_mult),
                   'FAC017_TWO_BAR_SHOCK_REVERSAL')
            for t, s, v in zip(times, sides, base)]

def run_batch(m1, year, out, limit=TOTAL):
    if type(year) is not int or year not in (2012, 2013):
        raise ValueError('Outside frozen design years')
    if type(limit) is not int or not 1 <= limit <= TOTAL:
        raise ValueError('Outside frozen grid')
    if limit > 100 and not HAS_JIT:
        raise RuntimeError('Numba required for bulk')
    out = Path(out)
    if (out/'summary.json').exists():
        raise FileExistsError('Refuse completed experiment overwrite')
    out.mkdir(parents=True, exist_ok=True)
    frozen = out/'frozen_spec.json'
    if frozen.exists() and json.loads(frozen.read_text()) != SPEC:
        raise ValueError('Conflicting frozen spec')
    frozen.write_text(json.dumps(SPEC, indent=2), encoding='utf-8')
    started = time.perf_counter()
    m15 = aggregate_bars(m1, 'M15')
    h1 = aggregate_bars(m1, 'H1')
    ht, hr = completed_h1_range_ratio(h1)
    stamps = np.asarray(m1.index.asi8//1_000_000_000, dtype=np.int64)
    op, hi, lo, cl = (m1[k].to_numpy(float) for k in ('o', 'h', 'l', 'c'))
    months = (m1.index.month.to_numpy(np.int16)-1).astype(np.int8)
    rows, cache, hashes = [], {}, set()
    for lookback, shock, retrace in itertools.product(LOOKBACKS, SHOCKS, RETRACES):
        times, sides, base = shock_reversal_signals(m15, lookback, shock, retrace)
        masks = local_session_masks(times)
        for regime, session in itertools.product(REGIMES, SESSIONS):
            t, s, b = causal_regime_session_gate(times, sides, base, ht, hr,
                                                 regime, session, masks)
            key = (lookback, shock, retrace, regime, session)
            cache[key] = (t, s, b)
            hashes.add(hashlib.sha256(t.tobytes()+s.tobytes()+b.tobytes()).hexdigest())
            for sm, tm in itertools.product(MULTS, MULTS):
                if len(rows) >= limit:
                    break
                monthly, fills, net, fees, dd, expired = replay_normalized(
                    stamps, op, hi, lo, cl, months, t, s, b, float(sm), float(tm))
                ident = (f'VSE17_N{lookback:02d}_Q{shock:.2f}_R{retrace:.2f}_'
                         f'{regime}_{session}_SL{sm:.2f}_TP{tm:.2f}')
                rows.append((ident, lookback, shock, retrace, regime, session,
                             sm, tm, len(t), expired, fills, net, fees, dd,
                             int((monthly > 0).sum()), float(monthly.min()),
                             *monthly.tolist()))
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    cols = ['id', 'lookback', 'shock', 'retrace', 'regime', 'session',
            'stop_mult', 'target_mult', 'signals', 'expired', 'trades',
            'net_usd_oz', 'fees_usd', 'max_m1_dd', 'positive_months',
            'worst_month'] + [f'm{i:02d}' for i in range(1, 13)]
    table = pd.DataFrame(rows, columns=cols)
    if not table.id.is_unique:
        raise AssertionError('Duplicate parameter IDs')
    monthly_cols = [f'm{i:02d}' for i in range(1, 13)]
    if not np.allclose(table.net_usd_oz, table[monthly_cols].sum(axis=1), atol=1e-7):
        raise AssertionError('Monthly reconciliation failed')
    if not np.allclose(table.fees_usd, .4*table.trades, atol=1e-7):
        raise AssertionError('Fee reconciliation failed')
    ranked = table.sort_values(['positive_months', 'worst_month', 'net_usd_oz'],
                               ascending=[False, False, False])
    picks = sorted(set([0, len(table)//2, len(table)-1, int(ranked.index[0])]))
    parity = []
    for ix in picks:
        row = table.iloc[ix]
        t, s, b = cache[(int(row.lookback), float(row.shock), float(row.retrace),
                         row.regime, row.session)]
        ref = run_fast(m1, canonical_signals(t, s, b, row.stop_mult, row.target_mult),
                       Settings(ounces=1., roundtrip_cost_per_ounce=.4))
        booked = np.bincount(pd.to_datetime(ref.trades.closed_at, utc=True).dt.month,
                             weights=ref.trades.net_pnl.to_numpy(float), minlength=13)[1:]
        expected = row[monthly_cols].to_numpy(float)
        month_error = float(np.max(np.abs(booked-expected)))
        equity = ref.equity.equity
        dd = float((equity.cummax().clip(lower=0)-equity).clip(lower=0).max())
        if (month_error > 1e-7 or abs(dd-row.max_m1_dd) > 1e-7 or
            len(ref.trades) != row.trades or
            abs(ref.trades.net_pnl.sum()-row.net_usd_oz) > 1e-7 or
            abs(ref.trades.cost.sum()-row.fees_usd) > 1e-7):
            raise AssertionError(f'FAC017 canonical parity failed: {row.id}')
        parity.append({'id': row.id, 'trades': int(row.trades),
                       'monthly_max_error': month_error,
                       'floating_dd_error': abs(dd-row.max_m1_dd)})
    table.to_csv(out/'all_candidates_monthly.csv', index=False)
    ranked.head(20).to_csv(out/'exploratory_top20_NOT_OOS.csv', index=False)
    summary = {'status': 'COMPLETED_EXPOSED_DESIGN_NOT_OOS', 'year': year,
               'executed_annual_replays': len(table),
               'active_annual_replays': int((table.trades > 0).sum()),
               'zero_trade_replays': int((table.trades == 0).sum()),
               'monthly_points_including_zero': len(table)*12,
               'unique_signal_streams': len(hashes),
               'max_positive_months': int(table.positive_months.max()),
               'positive_12_months': int((table.positive_months == 12).sum()),
               'positive_annual_net': int((table.net_usd_oz > 0).sum()),
               'loaded_m1_sha256': fingerprint_loaded_m1(m1),
               'original_zip_sha256': ORIGINAL,
               'canonical_run_fast_parity': parity,
               'elapsed_seconds': round(time.perf_counter()-started, 2),
               'warning': 'Historically exposed 2012/2013; correlated grid; no independent OOS.'}
    (out/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return table, summary

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold-zip', type=Path, required=True)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=TOTAL)
    args = parser.parse_args()
    if sha256_file(args.gold_zip) != ORIGINAL:
        raise ValueError('Original private Gold ZIP SHA256 mismatch')
    m1 = load_market(args.gold_zip, f'{args.year}-01-01', f'{args.year}-12-31')
    print(json.dumps(run_batch(m1, args.year, args.out, args.limit)[1], indent=2))

if __name__ == '__main__':
    main()
