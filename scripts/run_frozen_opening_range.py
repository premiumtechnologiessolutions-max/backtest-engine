"""Private-only preregistered ORB-01 design-year runner.

Never upload source quotes or generated trade ledgers to GitHub Actions.
Run with PYTHONPATH=src:. python -m scripts.run_frozen_opening_range
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.opening_range import OpeningRangeSettings, opening_range_signals
from norisk_quant.report import report

SOURCE_SHA = '1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121'
DESIGN_YEARS = (2012, 2013)
STRATEGY = OpeningRangeSettings()
EXECUTION = Settings(ounces=1.0, roundtrip_cost_per_ounce=0.40,
                     max_entry_delay_minutes=1, max_holding_minutes=360)
SPEC = {
    'research_id': 'ORB-01',
    'family': 'fixed_UTC_morning_opening_range_continuation',
    'design_years': list(DESIGN_YEARS),
    'strategy': vars(STRATEGY),
    'execution': {
        'ounces': 1.0, 'all_in_roundtrip_usd_per_ounce': 0.40,
        'max_entry_delay_minutes': 1, 'max_holding_minutes': 360,
        'stop_first': True, 'gap_through': True,
        'no_same_minute_reentry': True,
    },
    'acceptance': '>=18/24 positive exit-PnL months; >0 net in each year; >=75 trades each year',
    'independence': 'HISTORICALLY_EXPOSED_DESIGN_NOT_OOS',
}
SPEC_SHA = hashlib.sha256(json.dumps(
    SPEC, sort_keys=True, separators=(',', ':')
).encode()).hexdigest()


def execute(gold_zip: Path, year: int, out: Path) -> dict:
    if type(year) is not int or year not in DESIGN_YEARS:
        raise ValueError('ORB-01 frozen to 2012 and 2013 only')
    if sha256_file(gold_zip) != SOURCE_SHA:
        raise ValueError('Private original ZIP SHA mismatch')
    if out.exists():
        raise FileExistsError('Do not overwrite prior historical evaluation')
    market = load_market(gold_zip, f'{year}-01-01', f'{year}-12-31')
    signals = opening_range_signals(market, settings=STRATEGY)
    ref = run(market, signals, EXECUTION)
    fast = run_fast(market, signals, EXECUTION)
    pd.testing.assert_frame_equal(ref.trades, fast.trades, check_dtype=False,
                                  check_exact=False, atol=1e-7, rtol=0)
    # Preserve private provenance, but never publish proprietary bar/trade rows.
    fingerprint = fingerprint_loaded_m1(market)
    summary = report(ref, EXECUTION, out,
                     source='private_original_zip_sha256_verified',
                     provenance={'source_zip_sha256': SOURCE_SHA,
                                 'loaded_m1_sha256': fingerprint},
                     run_parameters={'frozen_spec_sha256': SPEC_SHA,
                                     'strategy': 'ORB-01'})
    if summary['months_observed'] != 12 or summary['months_with_m1_observations'] != 12:
        raise AssertionError('Incomplete annual monthly calendar')
    if abs(summary['total_fees'] - 0.40 * summary['trades']) > 1e-7:
        raise AssertionError('Fee reconciliation failed')
    audit = {
        'research_id': 'ORB-01', 'year': year, 'status': 'DESIGN_NOT_OOS',
        'source_sha256': SOURCE_SHA, 'm1_sha256': fingerprint,
        'm1_bars': len(market), 'spec_sha256': SPEC_SHA,
        'signals': len(signals), 'trades': summary['trades'],
        'positive_months': summary['positive_months'],
        'net_usd_per_oz': summary['net_pnl'],
        'max_m1_drawdown': summary['max_drawdown_observed_m1'],
        'total_fees': summary['total_fees'],
        'reference_fast_trade_parity': 'PASS',
        'broker_fill_validation': False,
    }
    (out / 'frozen_spec.json').write_text(json.dumps(SPEC, indent=2), encoding='utf-8')
    (out / 'year_scoreboard.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--gold-zip', type=Path, required=True)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.gold_zip, args.year, args.out), indent=2))


if __name__ == '__main__':
    main()
