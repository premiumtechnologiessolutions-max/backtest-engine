"""FAC018 preregistered session-anchor inventory unwind with completed H4 efficiency.

Freeze commit dc7f3cac1bffca61546678e18bf6d79e397c11d8 precedes outcomes.
2012/2013 are exposed design years, not OOS. Private original Gold ZIP only.
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
from scripts.batch_compression_h1_grid import replay_normalized

H4_WINDOWS = (4, 8, 12)
EXCURSIONS = (1., 1.5, 2., 2.5)
RETREATS = (.25, .4, .55)
REGIMES = ('RANGE', 'TRANSITION')
SESSIONS = ('LONDON_LOCAL_08_12', 'NY_LOCAL_0930_1330')
MULTS = tuple(.5 + .25 * i for i in range(8))
TOTAL = len(H4_WINDOWS) * len(EXCURSIONS) * len(RETREATS) * len(REGIMES) * len(SESSIONS) * len(MULTS)**2
PREREG = 'dc7f3cac1bffca61546678e18bf6d79e397c11d8'
SPEC = {
    'research_id': 'NRF-FAC-018', 'preregistration_commit': PREREG,
    'family': 'session-anchored typical-price inventory unwind gated by completed H4 path efficiency',
    'h4_windows': list(H4_WINDOWS), 'excursions': list(EXCURSIONS),
    'retreats': list(RETREATS), 'regimes': list(REGIMES),
    'sessions': list(SESSIONS), 'stop_mults': list(MULTS),
    'target_mults': list(MULTS), 'specs_per_year': TOTAL,
    'years': [2012, 2013], 'source_sha256': ORIGINAL,
    'roundtrip_all_in_usd_oz': .4, 'historically_exposed_not_oos': True,
    'acceptance': {'min_fills_each_year': 100, 'min_positive_months_of_24': 18,
                   'annual_net_positive_both': True, 'worst_month_min': -20.,
                   'annual_floating_dd_max': 100.},
}

def _empty():
    return np.empty(0, np.int64), np.empty(0, np.int8), np.empty(0, float)


def session_inventory_signals(m15, excursion, retreat, session):
    """Session starts at exact local clock; anchor through j-2, confirm at j close."""
    if (type(excursion) not in (float, int) or excursion not in EXCURSIONS or
        type(retreat) not in (float, int) or retreat not in RETREATS or
        session not in SESSIONS):
        raise ValueError('Nonfrozen FAC018 session parameters')
    if len(m15) < 24:
        return _empty()
    idx = m15.index
    if (not isinstance(idx, pd.DatetimeIndex) or idx.tz is None or
        str(idx.tz) != 'UTC' or not idx.is_unique or not idx.is_monotonic_increasing):
        raise ValueError('FAC018 requires monotone unique UTC M15')
    if (np.any(idx.asi8 % 900_000_000_000 != 0) or
        not np.array_equal(m15.close_at.array.asi8, idx.asi8 + 900_000_000_000)):
        raise ValueError('FAC018 requires complete aligned M15 bars')
    op, hi, lo, close = (m15[x].to_numpy(float) for x in ('o', 'h', 'l', 'c'))
    if not all(np.isfinite(x).all() for x in (op, hi, lo, close)):
        raise ValueError('Nonfinite M15 OHLC')
    ranges = hi - lo
    baseline = pd.Series(ranges).shift(2).rolling(20, min_periods=20).median().to_numpy()
    risk = pd.Series(ranges).shift(1).rolling(20, min_periods=20).median().to_numpy()
    segment = np.cumsum(np.r_[True, np.diff(idx.asi8) != 900_000_000_000])
    if session == 'LONDON_LOCAL_08_12':
        local, start, end = idx.tz_convert('Europe/London'), 480, 720
    else:
        local, start, end = idx.tz_convert('America/New_York'), 570, 810
    minute = np.asarray(local.hour * 60 + local.minute)
    active = (minute >= start) & (minute < end)
    positions = np.flatnonzero(active)
    if not len(positions):
        return _empty()
    # Each local calendar day is a separate inventory anchor; DST is resolved by tz_convert.
    local_days = np.asarray(local.date)
    typical = (hi + lo + close) / 3.
    stamps = np.asarray(m15.close_at.array.asi8 // 1_000_000_000, np.int64)
    signals = []
    for day in np.unique(local_days[positions]):
        group = positions[local_days[positions] == day]
        if len(group) < 4 or minute[group[0]] != start:
            continue
        # Reject remainder of session after the first missing observed M15 candle.
        gap = np.flatnonzero(np.diff(idx.asi8[group]) != 900_000_000_000)
        if len(gap):
            group = group[:int(gap[0]) + 1]
        if len(group) < 4:
            continue
        cumulative = np.cumsum(typical[group])
        for offset in range(3, len(group)):
            j = int(group[offset])
            if (j < 21 or segment[j] != segment[j-21] or
                minute[j] + 15 >= end or
                not np.isfinite(baseline[j]) or baseline[j] <= 0 or
                not np.isfinite(risk[j]) or risk[j] <= 0):
                continue
            # group[0] ... group[offset-2] excludes event j-1 and confirmation j.
            anchor = cumulative[offset-2] / (offset-1)
            displacement = close[j-1] - anchor
            if abs(displacement) < excursion * baseline[j]:
                continue
            if (displacement > 0 and close[j] < op[j] and
                anchor < close[j] <= close[j-1] - retreat * displacement):
                side = -1
            elif (displacement < 0 and close[j] > op[j] and
                  anchor > close[j] >= close[j-1] - retreat * displacement):
                side = 1
            else:
                continue
            signals.append((int(stamps[j]), side, float(risk[j])))
    if not signals:
        return _empty()
    t, s, b = zip(*signals)
    return np.asarray(t, np.int64), np.asarray(s, np.int8), np.asarray(b, float)


def completed_h4_efficiency(h4, window):
    """Causal H4 close-to-close path efficiency; gaps invalidate whole window."""
    if type(window) is not int or window not in H4_WINDOWS:
        raise ValueError('Nonfrozen FAC018 H4 lookback')
    if h4.empty:
        return np.empty(0, np.int64), np.empty(0, float)
    idx = h4.index
    if (idx.tz is None or str(idx.tz) != 'UTC' or not idx.is_unique or
        not idx.is_monotonic_increasing or
        not np.array_equal(h4.close_at.array.asi8, idx.asi8 + 14_400_000_000_000)):
        raise ValueError('Invalid H4 chronology')
    times = np.asarray(h4.close_at.array.asi8 // 1_000_000_000, np.int64)
    close = h4.c.to_numpy(float)
    efficiency = np.full(len(close), np.nan)
    for i in range(window-1, len(close)):
        if times[i] - times[i-window+1] != (window-1)*14400:
            continue
        path = close[i-window+1:i+1]
        if not np.isfinite(path).all():
            continue
        length = float(np.abs(np.diff(path)).sum())
        if length > 0:
            efficiency[i] = abs(float(path[-1]-path[0])) / length
    return times, efficiency


def causal_h4_gate(times, sides, base, h4times, efficiency, regime):
    """Last completed H4 <=4h old, halt for efficiency>0.65 or missing."""
    if regime not in REGIMES or not (len(times) == len(sides) == len(base)):
        raise ValueError('Nonfrozen regime or mismatched arrays')
    if not len(times) or not len(h4times):
        return _empty()
    if (np.any(np.diff(times) <= 0) or np.any(np.diff(h4times) <= 0) or
        np.any(~np.isin(sides, [-1, 1])) or len(h4times) != len(efficiency)):
        raise ValueError('Invalid causal arrays')
    last = np.searchsorted(h4times, times, side='right') - 1
    safe = np.maximum(last, 0)
    age = times - h4times[safe]
    eff = efficiency[safe]
    valid = (last >= 0) & (age >= 0) & (age <= 14400)
    valid &= np.isfinite(eff) & (eff >= 0) & (eff <= .65)
    if regime == 'RANGE':
        valid &= eff <= .35
    else:
        valid &= eff > .35
    return times[valid], sides[valid], base[valid]


def canonical_signals(times, sides, base, stop_mult, target_mult):
    return [Signal(pd.Timestamp(int(t), unit='s', tz='UTC'), int(s),
                   float(b*stop_mult), float(b*target_mult),
                   'FAC018_SESSION_INVENTORY_H4_EFFICIENCY')
            for t, s, b in zip(times, sides, base)]


def run_batch(m1, year, out, limit=TOTAL):
    if type(year) is not int or year not in (2012, 2013):
        raise ValueError('Outside frozen FAC018 years')
    if type(limit) is not int or not 1 <= limit <= TOTAL:
        raise ValueError('Outside frozen FAC018 grid')
    if limit > 100 and not HAS_JIT:
        raise RuntimeError('Numba required for bulk FAC018')
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
    h4 = aggregate_bars(m1, 'H4')
    stamps = np.asarray(m1.index.asi8 // 1_000_000_000, np.int64)
    op, hi, lo, cl = (m1[x].to_numpy(float) for x in ('o', 'h', 'l', 'c'))
    months = (m1.index.month.to_numpy(np.int16)-1).astype(np.int8)
    h4_context = {w: completed_h4_efficiency(h4, w) for w in H4_WINDOWS}
    event_cache = {(k, r, session): session_inventory_signals(m15, k, r, session)
                   for k, r, session in itertools.product(EXCURSIONS, RETREATS, SESSIONS)}
    gated = {}
    for window, k, r, regime, session in itertools.product(
            H4_WINDOWS, EXCURSIONS, RETREATS, REGIMES, SESSIONS):
        t, s, b = event_cache[(k, r, session)]
        ht, he = h4_context[window]
        gated[(window, k, r, regime, session)] = causal_h4_gate(t, s, b, ht, he, regime)
    rows, hashes = [], set()
    for key, (t, s, b) in gated.items():
        window, k, r, regime, session = key
        hashes.add(hashlib.sha256(t.tobytes()+s.tobytes()+b.tobytes()).hexdigest())
        for sm, tm in itertools.product(MULTS, MULTS):
            if len(rows) >= limit:
                break
            monthly, fills, net, fees, dd, expired = replay_normalized(
                stamps, op, hi, lo, cl, months, t, s, b, float(sm), float(tm))
            ident = (f'INV18_H{window:02d}_K{k:.2f}_R{r:.2f}_{regime}_{session}_'
                     f'SL{sm:.2f}_TP{tm:.2f}')
            rows.append((ident, window, k, r, regime, session, sm, tm,
                         len(t), expired, fills, net, fees, dd,
                         int((monthly > 0).sum()), float(monthly.min()),
                         *monthly.tolist()))
        if len(rows) >= limit:
            break
    cols = ['id', 'h4_window', 'excursion', 'retreat', 'regime', 'session',
            'stop_mult', 'target_mult', 'signals', 'expired', 'trades',
            'net_usd_oz', 'fees_usd', 'max_m1_dd', 'positive_months',
            'worst_month'] + [f'm{i:02d}' for i in range(1, 13)]
    table = pd.DataFrame(rows, columns=cols)
    if not table.id.is_unique:
        raise AssertionError('Duplicate FAC018 parameter ID')
    monthly_cols = [f'm{i:02d}' for i in range(1, 13)]
    if not np.allclose(table.net_usd_oz, table[monthly_cols].sum(axis=1), atol=1e-7):
        raise AssertionError('FAC018 monthly accounting mismatch')
    if not np.allclose(table.fees_usd, .4*table.trades, atol=1e-7):
        raise AssertionError('FAC018 ALL-IN fee mismatch')
    ranked = table.sort_values(['positive_months', 'worst_month', 'net_usd_oz'],
                               ascending=[False, False, False])
    picks = sorted(set([0, len(table)//2, len(table)-1, int(ranked.index[0])]))
    parity = []
    for ix in picks:
        row = table.iloc[ix]
        key = (int(row.h4_window), float(row.excursion), float(row.retreat),
               row.regime, row.session)
        t, s, b = gated[key]
        ref = run_fast(m1, canonical_signals(t, s, b, row.stop_mult, row.target_mult),
                       Settings(ounces=1., roundtrip_cost_per_ounce=.4))
        booked = np.bincount(pd.to_datetime(ref.trades.closed_at, utc=True).dt.month,
                             weights=ref.trades.net_pnl.to_numpy(float), minlength=13)[1:]
        expected = row[monthly_cols].to_numpy(float)
        err = float(np.max(np.abs(booked-expected)))
        equity = ref.equity.equity
        dd = float((equity.cummax().clip(lower=0)-equity).clip(lower=0).max())
        if (err > 1e-7 or abs(dd-row.max_m1_dd) > 1e-7 or
            len(ref.trades) != row.trades or
            abs(ref.trades.net_pnl.sum()-row.net_usd_oz) > 1e-7 or
            abs(ref.trades.cost.sum()-row.fees_usd) > 1e-7):
            raise AssertionError(f'FAC018 canonical mismatch: {row.id}')
        parity.append({'id': row.id, 'trades': int(row.trades),
                       'monthly_max_error': err,
                       'floating_dd_error': abs(dd-row.max_m1_dd)})
    table.to_csv(out/'all_candidates_monthly.csv', index=False)
    ranked.head(20).to_csv(out/'exploratory_top20_NOT_OOS.csv', index=False)
    summary = {
        'status': 'COMPLETED_EXPOSED_DESIGN_NOT_OOS', 'year': year,
        'executed_annual_replays': len(table),
        'active_annual_replays': int((table.trades > 0).sum()),
        'zero_trade_replays': int((table.trades == 0).sum()),
        'monthly_points_including_zero': len(table)*12,
        'unique_signal_streams': len(hashes),
        'max_positive_months': int(table.positive_months.max()),
        'positive_12_months': int((table.positive_months == 12).sum()),
        'loaded_m1_sha256': fingerprint_loaded_m1(m1),
        'original_zip_sha256': ORIGINAL,
        'canonical_run_fast_parity': parity,
        'elapsed_seconds': round(time.perf_counter()-started, 2),
        'warning': '2012/2013 exposed; correlated specs, not independent OOS.'}
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
        raise ValueError('Original Gold ZIP SHA mismatch')
    m1 = load_market(args.gold_zip, f'{args.year}-01-01', f'{args.year}-12-31')
    print(json.dumps(run_batch(m1, args.year, args.out, args.limit)[1], indent=2))


if __name__ == '__main__':
    main()
