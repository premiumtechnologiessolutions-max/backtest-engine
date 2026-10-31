"""FAC016 frozen, causal H1/H4 confirmed-pivot Fibonacci confluence grid.

FROZEN at commit 721387e06a81cfd47e0e33d5b31815a3dd6b0e96, before any
FAC016 source-data outcome. Exposed 2012/2013 design ONLY; never clean OOS.
Raw BID/ASK source remains local. No future pivot confirmation at pivot time.
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

PIVOT_PAIRS = ((2, 1), (2, 2), (3, 1), (3, 2))
FIBS = (.5, .62, .705, .79, .87)
TOLERANCES = (.5, 1., 1.5)
SESSIONS = ('ALL', 'LONDON_LOCAL_08_12', 'NY_LOCAL_0930_1330')
MULTS = tuple(.5 + .25*i for i in range(10))
TOTAL = len(PIVOT_PAIRS)*len(FIBS)*len(TOLERANCES)*len(SESSIONS)*len(MULTS)**2
PREREG = '721387e06a81cfd47e0e33d5b31815a3dd6b0e96'
SPEC = {
    'research_id': 'NRF-FAC-016', 'preregistration_commit': PREREG,
    'pivot_pairs_h1_h4': [list(p) for p in PIVOT_PAIRS],
    'fib_ratios': list(FIBS), 'tolerances': list(TOLERANCES),
    'sessions': list(SESSIONS), 'stop_mults': list(MULTS),
    'target_mults': list(MULTS), 'specs_per_year': TOTAL,
    'years': [2012, 2013], 'original_source_sha256': ORIGINAL,
    'roundtrip_all_in_usd_oz': .4, 'historically_exposed_not_oos': True,
    'acceptance': {'min_fills_each_year': 80, 'min_positive_months_of_24': 18,
                   'annual_net_positive_both': True, 'worst_month_min': -20.,
                   'annual_floating_dd_max': 100.}
}


def confirmed_pivot_waves(bars, width, tf_seconds, max_span_seconds):
    """Return confirmation time, direction, swing low/high for strictly confirmed pivots.

    A pivot at j is emitted only at the close of j+width, never at j.
    All 2*width+1 completed bars must be exactly contiguous.
    """
    if type(width) is not int or width not in (1, 2, 3):
        raise ValueError('Nonfrozen pivot width')
    if type(tf_seconds) is not int or tf_seconds not in (3600, 14400):
        raise ValueError('Invalid timeframe')
    if type(max_span_seconds) is not int or max_span_seconds <= 0:
        raise ValueError('Invalid span')
    empty = (np.empty(0, np.int64), np.empty(0, np.int8),
             np.empty(0, float), np.empty(0, float))
    if len(bars) < 2*width+1:
        return empty
    if bars.index.tz is None or str(bars.index.tz) != 'UTC':
        raise ValueError('Higher-timeframe bars require UTC')
    times = np.asarray(bars.index.asi8//1_000_000_000, dtype=np.int64)
    closed = np.asarray(bars.close_at.array.asi8//1_000_000_000, dtype=np.int64)
    high = bars.h.to_numpy(float)
    low = bars.l.to_numpy(float)
    if np.any(np.diff(times) <= 0) or np.any(closed != times+tf_seconds):
        raise ValueError('Invalid completed higher-timeframe timestamps')
    last_high = None
    last_low = None
    output = []
    for j in range(width, len(bars)-width):
        a, b = j-width, j+width+1
        if np.any(np.diff(times[a:b]) != tf_seconds):
            continue
        if not (np.isfinite(high[a:b]).all() and np.isfinite(low[a:b]).all()):
            continue
        if np.any(high[a:b] < low[a:b]):
            continue
        highs = np.r_[high[a:j], high[j+1:b]]
        lows = np.r_[low[a:j], low[j+1:b]]
        is_high = bool(np.all(high[j] > highs))
        is_low = bool(np.all(low[j] < lows))
        if is_high and is_low:
            continue  # outside-bar pivot is directionally ambiguous
        if is_high:
            last_high = (j, high[j])
        elif is_low:
            last_low = (j, low[j])
        else:
            continue
        if last_high is None or last_low is None:
            continue
        ih, hh = last_high
        il, ll = last_low
        if abs(times[ih]-times[il]) > max_span_seconds or hh <= ll:
            continue
        direction = 1 if ih > il else -1
        output.append((closed[j+width], direction, ll, hh))
    if not output:
        return empty
    arr = np.asarray(output, dtype=float)
    return (arr[:, 0].astype(np.int64), arr[:, 1].astype(np.int8),
            arr[:, 2].astype(float), arr[:, 3].astype(float))


def confluence_signals(m15, h1, h4, pivot_pair, fib, tolerance):
    """M15 close known; most recent confirmed H1/H4 waves known at that close."""
    if pivot_pair not in PIVOT_PAIRS or fib not in FIBS or tolerance not in TOLERANCES:
        raise ValueError('Nonfrozen FAC016 parameters')
    empty = (np.empty(0, np.int64), np.empty(0, np.int8), np.empty(0, float))
    if len(m15) < 21:
        return empty
    t1, s1, l1, h1hi = confirmed_pivot_waves(h1, pivot_pair[0], 3600, 168*3600)
    t4, s4, l4, h4hi = confirmed_pivot_waves(h4, pivot_pair[1], 14400, 672*3600)
    if not len(t1) or not len(t4):
        return empty
    stamps = np.asarray(m15.close_at.array.asi8//1_000_000_000, dtype=np.int64)
    opens = m15.o.to_numpy(float)
    closes = m15.c.to_numpy(float)
    ranges = (m15.h-m15.l).to_numpy(float)
    base = pd.Series(ranges).shift(1).rolling(20, min_periods=20).median().to_numpy()
    idx = np.arange(len(m15))
    segment = np.cumsum(np.r_[True, np.diff(m15.index.asi8)!=900_000_000_000])
    good = (idx >= 20) & (segment == segment[np.maximum(0, idx-20)])
    good &= np.isfinite(base) & (base > 0) & np.isfinite(opens) & np.isfinite(closes)
    p1 = np.searchsorted(t1, stamps, side='right')-1
    p4 = np.searchsorted(t4, stamps, side='right')-1
    q1 = np.maximum(p1, 0)
    q4 = np.maximum(p4, 0)
    age1 = stamps-t1[q1]
    age4 = stamps-t4[q4]
    good &= (p1 >= 0) & (p4 >= 0) & (age1 >= 0) & (age1 <= 72*3600)
    good &= (age4 >= 0) & (age4 <= 336*3600) & (s1[q1] == s4[q4])
    good &= ((closes-opens)*s1[q1] > 0)
    level1 = np.where(s1[q1] == 1, h1hi[q1]-fib*(h1hi[q1]-l1[q1]),
                      l1[q1]+fib*(h1hi[q1]-l1[q1]))
    level4 = np.where(s4[q4] == 1, h4hi[q4]-fib*(h4hi[q4]-l4[q4]),
                      l4[q4]+fib*(h4hi[q4]-l4[q4]))
    good &= np.abs(closes-level1) <= tolerance*base
    good &= np.abs(closes-level4) <= tolerance*base
    chosen = np.flatnonzero(good)
    return stamps[chosen], s1[q1[chosen]].astype(np.int8), base[chosen]


def canonical_signals(times, sides, base, stop_mult, target_mult):
    return [Signal(pd.Timestamp(int(t), unit='s', tz='UTC'), int(s),
                   float(v*stop_mult), float(v*target_mult),
                   'FAC016_H1_H4_CONFIRMED_FIB')
            for t, s, v in zip(times, sides, base)]


def run_batch(m1, year, out, limit=TOTAL):
    if type(year) is not int or year not in (2012, 2013):
        raise ValueError('Outside frozen years')
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
    h4 = aggregate_bars(m1, 'H4')
    stamps = np.asarray(m1.index.asi8//1_000_000_000, dtype=np.int64)
    op, hi, lo, cl = (m1[k].to_numpy(float) for k in ('o', 'h', 'l', 'c'))
    months = (m1.index.month.to_numpy(np.int16)-1).astype(np.int8)
    rows, cache, signal_hashes = [], {}, set()
    for pair, fib, tolerance in itertools.product(PIVOT_PAIRS, FIBS, TOLERANCES):
        t, s, v = confluence_signals(m15, h1, h4, pair, fib, tolerance)
        masks = local_session_masks(t)
        for session in SESSIONS:
            keep = masks[session]
            st, sd, sv = t[keep], s[keep], v[keep]
            key = (pair, fib, tolerance, session)
            cache[key] = (st, sd, sv)
            signal_hashes.add(hashlib.sha256(st.tobytes()+sd.tobytes()+sv.tobytes()).hexdigest())
            for sm, tm in itertools.product(MULTS, MULTS):
                if len(rows) >= limit:
                    break
                monthly, fills, net, fees, dd, expired = replay_normalized(
                    stamps, op, hi, lo, cl, months, st, sd, sv, float(sm), float(tm))
                ident = (f'FIB16_H{pair[0]}_H4{pair[1]}_F{fib:.3f}_T{tolerance:.2f}_'
                         f'{session}_SL{sm:.2f}_TP{tm:.2f}')
                rows.append((ident, pair[0], pair[1], fib, tolerance, session,
                             sm, tm, len(st), expired, fills, net, fees, dd,
                             int((monthly > 0).sum()), float(monthly.min()), *monthly.tolist()))
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    cols = ['id', 'h1_pivot_width', 'h4_pivot_width', 'fib', 'tolerance', 'session',
            'stop_mult', 'target_mult', 'signals', 'expired', 'trades', 'net_usd_oz',
            'fees_usd', 'max_m1_dd', 'positive_months', 'worst_month'] + [
                f'm{i:02d}' for i in range(1, 13)]
    table = pd.DataFrame(rows, columns=cols)
    if not table.id.is_unique:
        raise AssertionError('Duplicate parameter IDs')
    if not np.allclose(table.net_usd_oz,
                       table[[f'm{i:02d}' for i in range(1, 13)]].sum(axis=1),
                       atol=1e-7):
        raise AssertionError('Monthly reconciliation failed')
    if not np.allclose(table.fees_usd, .4*table.trades, atol=1e-7):
        raise AssertionError('Fee reconciliation failed')
    ranked = table.sort_values(['positive_months', 'worst_month', 'net_usd_oz'],
                               ascending=[False, False, False])
    picks = sorted(set([0, len(table)//2, len(table)-1, int(ranked.index[0])]))
    parity = []
    for ix in picks:
        row = table.iloc[ix]
        key = ((int(row.h1_pivot_width), int(row.h4_pivot_width)),
               float(row.fib), float(row.tolerance), row.session)
        st, sd, sv = cache[key]
        ref = run_fast(m1, canonical_signals(st, sd, sv, row.stop_mult, row.target_mult),
                       Settings(ounces=1., roundtrip_cost_per_ounce=.4))
        booked = np.bincount(pd.to_datetime(ref.trades.closed_at, utc=True).dt.month,
                             weights=ref.trades.net_pnl.to_numpy(float), minlength=13)[1:]
        expected = row[[f'm{i:02d}' for i in range(1, 13)]].to_numpy(float)
        month_error = float(np.max(np.abs(booked-expected)))
        equity = ref.equity.equity
        dd = float((equity.cummax().clip(lower=0)-equity).clip(lower=0).max())
        if (month_error > 1e-7 or abs(dd-row.max_m1_dd) > 1e-7
                or len(ref.trades) != row.trades
                or abs(ref.trades.net_pnl.sum()-row.net_usd_oz) > 1e-7
                or abs(ref.trades.cost.sum()-row.fees_usd) > 1e-7):
            raise AssertionError(f'Canonical mismatch {row.id}')
        parity.append({'id': row.id, 'trades': int(row.trades),
                       'max_month_error': month_error,
                       'floating_dd_error': abs(dd-row.max_m1_dd)})
    table.to_csv(out/'all_candidates_monthly.csv', index=False)
    ranked.head(20).to_csv(out/'exploratory_top20_NOT_OOS.csv', index=False)
    summary = {'status': 'COMPLETED_EXPOSED_DESIGN_NOT_OOS', 'year': year,
               'executed_annual_replays': len(table),
               'active_annual_replays': int((table.trades > 0).sum()),
               'zero_trade_replays': int((table.trades == 0).sum()),
               'monthly_points': len(table)*12,
               'unique_signal_streams': len(signal_hashes),
               'positive_annual_net_specs': int((table.net_usd_oz > 0).sum()),
               'max_positive_months': int(table.positive_months.max()),
               'configs_12_of_12': int((table.positive_months == 12).sum()),
               'original_source_sha256': ORIGINAL,
               'loaded_m1_sha256': fingerprint_loaded_m1(m1),
               'canonical_run_fast_parity': parity,
               'elapsed_seconds': round(time.perf_counter()-started, 2),
               'warning': 'Exposed 2012/2013 design only; correlated specs, not OOS.'}
    (out/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return table, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gold-zip', type=Path, required=True)
    p.add_argument('--year', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--limit', type=int, default=TOTAL)
    args = p.parse_args()
    if sha256_file(args.gold_zip) != ORIGINAL:
        raise ValueError('Original private ZIP SHA mismatch')
    m1 = load_market(args.gold_zip, f'{args.year}-01-01', f'{args.year}-12-31')
    print(json.dumps(run_batch(m1, args.year, args.out, args.limit)[1], indent=2))


if __name__ == '__main__':
    main()
