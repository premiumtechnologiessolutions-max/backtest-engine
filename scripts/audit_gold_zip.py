"""Read-only XAUUSD annual source audit; does not need pyarrow or write prices."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd


def audit(zip_path: Path, year: int) -> dict:
    with zipfile.ZipFile(zip_path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith('.json') and Path(n).stem.split(' ')[0] == str(year)]
        if len(members) != 1:
            raise ValueError(f'Expected exactly one JSON source member for {year}, found {members}')
        name = members[0]
        raw = archive.read(name)
    frame = pd.DataFrame.from_records(json.loads(raw))
    required = {'ts', 'o', 'h', 'l', 'c', 'ao', 'ah', 'al', 'ac'}
    if not required.issubset(frame):
        raise ValueError(f'Missing columns: {sorted(required - set(frame))}')
    frame['dt'] = pd.to_datetime(frame.ts, unit='s', utc=True, errors='raise')
    frame = frame.sort_values('dt')
    delta = frame.ts.diff().dropna().div(60)
    bid_bad = (frame.h < frame[['o', 'l', 'c']].max(axis=1)) | (frame.l > frame[['o', 'h', 'c']].min(axis=1))
    ask_bad = (frame.ah < frame[['ao', 'al', 'ac']].max(axis=1)) | (frame.al > frame[['ao', 'ah', 'ac']].min(axis=1))
    large = delta[delta > 10]
    report = {
        'year': year,
        'source_member': name,
        'source_member_sha256': hashlib.sha256(raw).hexdigest(),
        'rows': int(len(frame)),
        'first_utc': frame.dt.iloc[0].isoformat(),
        'last_utc': frame.dt.iloc[-1].isoformat(),
        'wrong_year_rows': int((frame.dt.dt.year != year).sum()),
        'duplicate_timestamps': int(frame.ts.duplicated().sum()),
        'off_minute_timestamps': int((frame.ts % 60 != 0).sum()),
        'non_60s_intervals': int((delta != 1).sum()),
        'gaps_over_10min': int((delta > 10).sum()),
        'missing_observed_minutes_including_market_closures': int((delta - 1).clip(lower=0).sum()),
        'gaps_10_to_120min': int(((delta > 10) & (delta <= 120)).sum()),
        'gaps_120_to_1000min': int(((delta > 120) & (delta <= 1000)).sum()),
        'gaps_over_1000min': int((delta > 1000).sum()),
        'common_gap_intervals_min': {str(int(k)): int(v) for k, v in large.value_counts().head(8).items()},
        'bid_ohlc_anomalies': int(bid_bad.sum()),
        'ask_ohlc_anomalies': int(ask_bad.sum()),
        'ask_below_bid_open': int((frame.ao < frame.o).sum()),
        'ask_below_bid_close': int((frame.ac < frame.c).sum()),
        'ask_below_bid_high': int((frame.ah < frame.h).sum()),
        'ask_below_bid_low': int((frame.al < frame.l).sum()),
        'note': 'Observed gaps include ordinary market closures. This does not validate execution or backtest profitability.',
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', required=True, type=Path)
    parser.add_argument('--year', required=True, type=int)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = audit(args.zip, args.year)
    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + '\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
