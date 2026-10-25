from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import import_gold_zip, load_market, quality, read_source
from .execution import run
from .gaps import classify_index_gaps
from .model import Settings
from .report import report
from .strategy import ema_cross_signals


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="norisk",
        description="No Risk FX research backtesting (not live execution)",
    )
    subs = parser.add_subparsers(dest="command", required=True)
    ingest = subs.add_parser("import-gold", help="Import annual JSON source ZIP to versioned Parquet")
    ingest.add_argument("zip_file")
    ingest.add_argument("--out", required=True)

    audit = subs.add_parser("audit", help="Audit one source JSON/CSV/Parquet")
    audit.add_argument("source")

    gap_audit = subs.add_parser(
        "audit-gaps",
        help="Classify time gaps by NY trading-hour PATTERN; holiday hints are unverified",
    )
    gap_audit.add_argument("--data", required=True, help="Imported Parquet directory or source file")
    gap_audit.add_argument("--start", required=True, help="UTC inclusive YYYY-MM-DD")
    gap_audit.add_argument("--end", required=True, help="UTC inclusive YYYY-MM-DD")
    gap_audit.add_argument("--out", required=True, help="Destination directory")
    gap_audit.add_argument("--min-missing-minutes", type=int, default=10)

    test = subs.add_parser("backtest", help="Run EMA example on M1 data (research smoke model)")
    test.add_argument("--data", required=True)
    test.add_argument("--start", required=True, help="UTC inclusive YYYY-MM-DD")
    test.add_argument("--end", required=True, help="UTC inclusive YYYY-MM-DD")
    test.add_argument("--out", required=True)
    test.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "H1", "H4"))
    test.add_argument("--fast", type=int, default=9)
    test.add_argument("--slow", type=int, default=21)
    test.add_argument("--stop-atr", type=float, default=1.5)
    test.add_argument("--rr", type=float, default=2.0)
    test.add_argument("--ounces", type=float, default=1.0)
    test.add_argument("--all-in-cost-per-ounce", type=float, default=0.40)

    args = parser.parse_args()
    if args.command == "import-gold":
        manifest = import_gold_zip(args.zip_file, args.out)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    elif args.command == "audit":
        # Strict parsing rejects anomalous candles; detailed ZIP partition
        # audits are persisted during import-gold.
        frame = read_source(args.source)
        print(json.dumps(quality(frame), ensure_ascii=False, indent=2))
    elif args.command == "audit-gaps":
        frame = load_market(args.data, args.start, args.end)
        catalogue = classify_index_gaps(
            frame.index, min_missing_minutes=args.min_missing_minutes
        )
        destination = Path(args.out)
        destination.mkdir(parents=True, exist_ok=True)
        catalogue.to_csv(destination / "gap_catalogue.csv", index=False)
        catalogue[catalogue["needs_review"]].to_csv(
            destination / "gap_manual_review.csv", index=False
        )
        counts = catalogue["classification"].value_counts().to_dict()
        summary = {
            "instrument": "XAUUSD",
            "source": args.data,
            "start_utc": frame.index.min().isoformat(),
            "end_utc": frame.index.max().isoformat(),
            "min_missing_minutes_exclusive": args.min_missing_minutes,
            "total_gaps": int(len(catalogue)),
            "needs_review": int(catalogue["needs_review"].sum()),
            "classification_counts": {k: int(v) for k, v in counts.items()},
            "important_warning": (
                "Matching a NY time pattern or holiday calendar does not verify "
                "historical broker hours or prove the cause of a feed interruption."
            ),
        }
        (destination / "gap_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.command == "backtest":
        data = load_market(args.data, args.start, args.end)
        settings = Settings(
            ounces=args.ounces,
            roundtrip_cost_per_ounce=args.all_in_cost_per_ounce,
        )
        signals = ema_cross_signals(
            data, timeframe=args.timeframe, fast=args.fast,
            slow=args.slow, stop_atr=args.stop_atr, rr=args.rr,
        )
        result = run(data, signals, settings)
        summary = report(result, settings, args.out, source=str(Path(args.data)))
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
