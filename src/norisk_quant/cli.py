from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .data import import_gold_zip, load_market, quality, read_source, fingerprint_loaded_m1, sha256_file
from .bos_fib import BosFibSettings, bos_fib_limit_orders
from .h1_regime import H1RegimeSettings, filter_orders_h1
from .qs01 import qs01_signals
from .quote_stress import qs01_settings
from .execution import run
from .fast_engine import run_fast
from .fvg import fvg_midpoint_limit_orders
from .limit_engine import run_limits
from .gaps import classify_index_gaps
from .model import Settings
from .report import report
from .registry import ExperimentIdentity, experiment_manifest
from .strategy import ema_cross_signals
from .strategies_native import donchian_breakout_signals
from .ticks import TickSource, audit_tick_csv
from .walkforward import year_folds, fold_manifest


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

    tick_audit = subs.add_parser(
        "audit-ticks",
        help="Audit external timestamped Bid/Ask quote ticks; does not run tick fills",
    )
    tick_audit.add_argument("--csv", required=True)
    tick_audit.add_argument("--provider", required=True)
    tick_audit.add_argument("--symbol", default="XAUUSD")
    tick_audit.add_argument("--source-kind", default="declared_broker_ticks",
                            choices=["declared_broker_ticks", "exchange_ticks"])
    tick_audit.add_argument("--out", required=True)

    fold_plan = subs.add_parser(
        "plan-walkforward", help="Export embargoed research folds; not proof of OOS"
    )
    fold_plan.add_argument("--start-year", type=int, default=2012)
    fold_plan.add_argument("--last-year", type=int, default=2024)
    fold_plan.add_argument("--min-training-years", type=int, default=5)
    fold_plan.add_argument("--embargo-days", type=int, default=14)
    fold_plan.add_argument("--out", required=True)

    identify = subs.add_parser(
        "identify-experiment",
        help="Make a deterministic ID for a versioned experiment; does NOT run a backtest",
    )
    identify.add_argument("--spec", required=True, help="JSON file matching ExperimentIdentity")
    identify.add_argument("--out", required=True)

    test = subs.add_parser("backtest", help="Run EMA example on M1 data (research smoke model)")
    test.add_argument("--data", required=True)
    test.add_argument("--start", required=True, help="UTC inclusive YYYY-MM-DD")
    test.add_argument("--end", required=True, help="UTC inclusive YYYY-MM-DD")
    test.add_argument("--out", required=True)
    test.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "H1", "H4"))
    test.add_argument("--strategy", default="ema", choices=("ema", "donchian", "fvg", "bos-fib", "qs01"))
    test.add_argument("--execution", default="reference", choices=("reference", "fast"))
    test.add_argument("--donchian-lookback", type=int, default=20)
    test.add_argument("--stop-usd", type=float, default=15.0)
    test.add_argument("--target-usd", type=float, default=30.0)
    test.add_argument("--fvg-min-gap-usd", type=float, default=0.5)
    test.add_argument("--fvg-stop-buffer-usd", type=float, default=0.1)
    test.add_argument("--fvg-rr", type=float, default=2.0)
    test.add_argument("--fvg-expiry-hours", type=float, default=20.0)
    test.add_argument("--bos-pivot-left", type=int, default=3)
    test.add_argument("--bos-pivot-right", type=int, default=3)
    test.add_argument("--bos-fib-entry", type=float, default=0.618)
    test.add_argument("--bos-rr", type=float, default=1.0)
    test.add_argument("--bos-stop-buffer-usd", type=float, default=0.10)
    test.add_argument("--bos-min-break-usd", type=float, default=0.10)
    test.add_argument("--bos-min-impulse-usd", type=float, default=1.0)
    test.add_argument("--bos-expiry-minutes", type=int, default=120)
    test.add_argument("--bos-min-gross-reward-fee-multiple", type=float, default=0.0)
    test.add_argument("--bos-require-h1-trend", action="store_true", help="Use fully closed H1 EMA50 slope5 filter")
    test.add_argument("--bos-h1-max-age-minutes", type=int, default=None, help="Reject stale H1 regime after a quote closure (opt-in; e.g. 120)")
    test.add_argument("--bos-ignore-dual-pivots", action="store_true", help="Exclude swing candles that are both M1 pivot high and low")
    test.add_argument("--fast", type=int, default=9)
    test.add_argument("--slow", type=int, default=21)
    test.add_argument("--stop-atr", type=float, default=1.5)
    test.add_argument("--rr", type=float, default=2.0)
    test.add_argument("--ounces", type=float, default=1.0)
    test.add_argument("--all-in-cost-per-ounce", type=float, default=0.40)

    args = parser.parse_args()
    # Canonical No Risk FX strategy research uses ONE declared full-cycle
    # ALL-IN $0.40/oz fee. Reject accidental $0 or double-fee estimates.
    if args.command == "backtest" and args.all_in_cost_per_ounce != 0.40:
        parser.error(
            "Canonical XAUUSD research requires exactly $0.40/oz ALL-IN "
            "round-trip; do not disable or layer on another spread/fee."
        )
    if args.command == "backtest" and args.strategy == "qs01" and (
        args.timeframe != "M1" or args.ounces != 1.0
    ):
        parser.error("Frozen QS01 requires --timeframe M1 and --ounces 1")
    # A requested engine must be the engine that actually executes the run.
    # Limit strategies use run_limits() regardless of --execution; previously
    # --execution fast was silently accepted and recorded in run_parameters.
    if args.command == "backtest" and args.execution == "fast" and args.strategy in ("bos-fib", "fvg"):
        parser.error(
            "--execution fast is not implemented for limit strategies "
            "(bos-fib, fvg); use --execution reference"
        )
    # Never record H1/BOS controls that were silently ignored. These
    # validation errors occur before opening private market data.
    if args.command == "backtest":
        if args.strategy != "bos-fib" and (
            args.bos_require_h1_trend or args.bos_h1_max_age_minutes is not None
            or args.bos_ignore_dual_pivots
        ):
            parser.error("BOS/H1 filters require --strategy bos-fib")
        if args.bos_h1_max_age_minutes is not None:
            if args.bos_h1_max_age_minutes < 0:
                parser.error("--bos-h1-max-age-minutes must be nonnegative")
            if not args.bos_require_h1_trend:
                parser.error(
                    "--bos-h1-max-age-minutes requires --bos-require-h1-trend"
                )
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
    elif args.command == "audit-ticks":
        declared = TickSource(
            provider=args.provider, symbol=args.symbol, source_kind=args.source_kind,
        )
        summary = audit_tick_csv(args.csv, declared)
        dest = Path(args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    elif args.command == "plan-walkforward":
        folds = year_folds(
            start_year=args.start_year,
            last_year=args.last_year,
            minimum_train_years=args.min_training_years,
            embargo_days=args.embargo_days,
        )
        dest = Path(args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps({
                "folds": fold_manifest(folds),
                "validation_status": "PLANNED_ONLY_NO_RESULT_IS_INDEPENDENT",
            }, indent=2), encoding="utf-8"
        )
        print(json.dumps({"folds": len(folds), "written": str(dest)}, indent=2))
    elif args.command == "identify-experiment":
        params = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        identity = ExperimentIdentity(**params)
        manifest = experiment_manifest(identity)
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    elif args.command == "backtest":
        data = load_market(args.data, args.start, args.end)
        settings = qs01_settings() if args.strategy == "qs01" else Settings(
            ounces=args.ounces,
            roundtrip_cost_per_ounce=args.all_in_cost_per_ounce,
        )
        if args.strategy == "bos-fib":
            if args.timeframe != "M1":
                raise ValueError("BOS/Fib variant is defined on M1 only; use --timeframe M1")
            params = BosFibSettings(
                pivot_left=args.bos_pivot_left,
                pivot_right=args.bos_pivot_right,
                fib_entry=args.bos_fib_entry,
                reward_risk=args.bos_rr,
                sl_buffer_usd=args.bos_stop_buffer_usd,
                min_break_usd=args.bos_min_break_usd,
                min_impulse_usd=args.bos_min_impulse_usd,
                expiry_minutes=args.bos_expiry_minutes,
                min_gross_reward_fee_multiple=args.bos_min_gross_reward_fee_multiple,
                all_in_cost_per_ounce=args.all_in_cost_per_ounce,
                ignore_ambiguous_dual_pivots=args.bos_ignore_dual_pivots,
            )
            limit_orders = bos_fib_limit_orders(data, settings=params)
            if args.bos_require_h1_trend:
                limit_orders = filter_orders_h1(
                    data, limit_orders, cfg=H1RegimeSettings(
                        ema_span=50, slope_lag_bars=5,
                        max_regime_age_minutes=args.bos_h1_max_age_minutes,
                    )
                )
            result = run_limits(data, limit_orders, settings)
        elif args.strategy == "qs01":
            signals = qs01_signals(data)
            result = (run_fast if args.execution == "fast" else run)(data, signals, settings)
        elif args.strategy == "fvg":
            limit_orders = fvg_midpoint_limit_orders(
                data,
                timeframe=args.timeframe,
                min_gap_usd=args.fvg_min_gap_usd,
                stop_buffer_usd=args.fvg_stop_buffer_usd,
                reward_to_risk=args.fvg_rr,
                expiry_hours=args.fvg_expiry_hours,
            )
            result = run_limits(data, limit_orders, settings)
        else:
            if args.strategy == "ema":
                signals = ema_cross_signals(
                    data, timeframe=args.timeframe, fast=args.fast,
                    slow=args.slow, stop_atr=args.stop_atr, rr=args.rr,
                )
            else:
                signals = donchian_breakout_signals(
                    data, timeframe=args.timeframe, lookback=args.donchian_lookback,
                    stop_distance=args.stop_usd, target_distance=args.target_usd,
                )
            result = (run_fast if args.execution == "fast" else run)(data, signals, settings)
        data_path = Path(args.data)
        source_file_sha = sha256_file(data_path) if data_path.is_file() else None
        manifest_sha = None
        manifest_file = data_path / "manifest.json" if data_path.is_dir() else None
        if manifest_file is not None and manifest_file.is_file():
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest_sha = manifest.get("source_sha256")
        provenance = {
            "loaded_m1_bidask_sha256": fingerprint_loaded_m1(data),
            "loaded_m1_rows": int(len(data)),
            "source_file_sha256": source_file_sha,
            "source_archive_sha256_from_manifest": manifest_sha,
            "cache_integrity_status": data.attrs.get("cache_integrity"),
            # CI can provide GITHUB_SHA; local runs must record their
            # full repository commit separately if this is unspecified.
            "git_revision_env": os.environ.get("GITHUB_SHA") or None,
        }
        settings_for_run = {
            key: value for key, value in vars(args).items()
            if key not in ("data", "out")
        }
        summary = report(
            result, settings, args.out, source=str(data_path),
            provenance=provenance, run_parameters=settings_for_run,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
