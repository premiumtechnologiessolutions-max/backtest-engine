"""Original-quote FAC025-ENTRY-A structural feasibility, never a trade replay.

No receipt-time authentication, fills, P/L, one-slot portfolio or OOS claims.
Requires private source SHA; only aggregated counts may be published.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import zipfile

SOURCE_SHA = '1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121'
MINUTE, QUARTER, HOUR = 60, 900, 3600


def inspect_year(rows):
    """Count strictly completed, contiguous historical BID M15/H1 contexts.

    Rows must be original-source format (UTC epoch-minute opens, BID/ASK OHLC).
    The candidate M15 must have closed before the prospective decision.
    This diagnostic intentionally does not use frozen session/receipt/loss gates.
    """
    bars, opens = {}, set()
    previous, group_start, group, contiguous = None, None, [], True
    counts = Counter()

    def flush():
        if not group:
            return
        if len(group) == 15 and contiguous and group[0]['ts'] == group_start and group[-1]['ts'] == group_start + 14 * MINUTE:
            end = group_start + QUARTER
            bars[end] = (max(x['h'] for x in group), min(x['l'] for x in group), group[-1]['c'])
            counts['complete_m15'] += 1

    for row in rows:
        if type(row) is not dict or any(k not in row for k in ('ts','o','h','l','c','ao','ah','al','ac')):
            raise ValueError('Malformed source row')
        t = row['ts']
        if type(t) is not int or t % MINUTE or (previous is not None and t <= previous):
            raise ValueError('Unaligned, unsorted or duplicate source minute')
        for prefix in ('', 'a'):
            o,h,l,c = (row[prefix+k] for k in ('o','h','l','c'))
            if any(type(x) not in (float,int) or not (0 < x < float('inf')) for x in (o,h,l,c)) or not l <= min(o,c) <= max(o,c) <= h:
                raise ValueError('Invalid source quote OHLC')
        if any(row['a'+k] < row[k] for k in ('o','h','l','c')):
            raise ValueError('Crossed BID/ASK source OHLC')
        opens.add(t)
        start = t // QUARTER * QUARTER
        if start != group_start:
            flush()
            group_start, group, contiguous = start, [], True
        if group and t != group[-1]['ts'] + MINUTE:
            contiguous = False
        group.append(row)
        previous = t
        counts['observed_m1'] += 1
    flush()

    months = {}
    for end in sorted(bars):
        previous_four = [bars.get(end - QUARTER*k) for k in (4,3,2,1)]
        if any(x is None for x in previous_four):
            continue
        counts['complete_sweep_context'] += 1
        candidate = bars[end]
        candidate_start = end - QUARTER
        h1_cutoff = candidate_start // HOUR * HOUR
        def h1_close(h1_end):
            four = [bars.get(h1_end - QUARTER*k) for k in (3,2,1,0)]
            return four[-1][2] if all(x is not None for x in four) else None
        older, newer = h1_close(h1_cutoff-HOUR), h1_close(h1_cutoff)
        if older is None or newer is None:
            continue
        counts['complete_two_prior_h1_context'] += 1
        low_prior = min(x[1] for x in previous_four)
        high_prior = max(x[0] for x in previous_four)
        bull = candidate[1] < low_prior < candidate[2] and newer > older
        bear = candidate[0] > high_prior > candidate[2] and newer < older
        if bull == bear:
            continue
        counts['sweep_h1_directional_candidates'] += 1
        close = candidate[2]
        wick = close - candidate[1] if bull else candidate[0] - close
        stop = max(wick, close * 0.0004)
        if stop > close * 0.0015:
            counts['normalized_risk_rejected'] += 1
            continue
        counts['normalized_risk_passed_intents'] += 1
        # Diagnostic only: after M15 end, decision at end+60s and
        # strictly subsequent M1 open at end+120s; not an actual fill.
        next_open_observed = (end + 2*MINUTE) in opens
        if next_open_observed:
            counts['next_minute_open_observed_not_fill'] += 1
        month = datetime.fromtimestamp(end, timezone.utc).strftime('%Y-%m')
        m = months.setdefault(month, {'candidates':0, 'next_open_observed':0})
        m['candidates'] += 1
        m['next_open_observed'] += int(next_open_observed)
    return {'counts': dict(counts), 'months': months}


def run_source(zip_path, years):
    path = Path(zip_path)
    digest = sha256(path.read_bytes()).hexdigest()
    if digest != SOURCE_SHA:
        raise ValueError('Private Gold ZIP SHA256 mismatch')
    results = {}
    with zipfile.ZipFile(path) as archive:
        for year in years:
            rows = json.loads(archive.read(f'{year}.json'))
            results[str(year)] = inspect_year(rows)
    return {'status':'SOURCE_ONLY_STRUCTURAL_FEASIBILITY_NOT_BACKTEST',
            'source_sha256':digest, 'frozen_policy':'FAC025-ENTRY-A',
            'execution_verified':False,'receipts_authenticated':False,
            'portfolio_capacity_verified':False,'monthly_pnl':'N/A',
            'floating_drawdown':'N/A','approved_strategies':0,
            'years':results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('private_zip')
    parser.add_argument('--years', nargs='+', type=int, default=[2012,2013,2014,2015,2016])
    args = parser.parse_args()
    print(json.dumps(run_source(args.private_zip,args.years),indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
