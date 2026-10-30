"""Execute a verified arithmetic generation on *exposed training years only*.

Requires a local authorized data archive and the original frozen training
input. Runs the canonical CLI twice (reference and fast), audits both output
trees, and publishes a batch atomically. Not an OOS or broker-fill certificate.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import pandas as pd

from norisk_quant.math_discovery import Formula
from scripts.materialize_arithmetic_generation import materialize, _load_strict

SCHEMA = "NRFX_ARITHMETIC_TRAINING_REPLAY_V1"
SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
SHA = re.compile(r"[0-9a-f]{64}\Z")
REPORTS = ("trades.csv", "monthly.csv", "weekly.csv", "equity_m1.csv",
           "gap_catalogue.csv")
SUMMARY_KEYS = (
    "trades", "net_pnl", "total_fees", "positive_months",
    "months_observed", "months_with_m1_observations",
    "max_drawdown_observed_m1", "last_observed_equity",
    "last_observed_realized_pnl", "accounting_checks",
    "forced_end_of_data_closures", "same_entry_bar_target_deferred",
    "trades_exposed_to_uncertain_gaps",
)
TRADE_FIELDS = (
    "strategy", "signal_at", "entry_at", "closed_at", "side",
    "entry_price", "exit_price", "stop", "target", "ounces",
    "gross_pnl", "cost", "net_pnl", "exit_reason", "gap_minutes",
)


def _digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_destination(path: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlink output path is forbidden")
    if path.exists():
        raise ValueError("Frozen replay destination already exists")


def _strict_formula(path: Path, expected: dict) -> None:
    source, digest = _load_strict(path)
    if digest != expected["file_sha256"] or type(source) is not dict:
        raise ValueError("Frozen dispatch formula SHA mismatch")
    formula = Formula(**source)
    if formula.identity() != expected["identity"]:
        raise ValueError("Frozen dispatch formula identity mismatch")


def _verify_trade_accounting(trades: pd.DataFrame) -> None:
    """Independent per-row accounting and chronology, even if both engines agree."""
    for row in trades.itertuples(index=False):
        if (row.side not in (-1, 1) or int(row.side) != row.side
                or row.gap_minutes < 0 or int(row.gap_minutes) != row.gap_minutes):
            raise ValueError("Invalid trade direction or gap minutes")
        numbers = (row.entry_price, row.exit_price, row.stop, row.target,
                   row.ounces, row.gross_pnl, row.cost, row.net_pnl)
        if not all(math.isfinite(float(value)) for value in numbers):
            raise ValueError("Nonfinite trade execution field")
        if (row.ounces <= 0 or min(row.entry_price, row.exit_price,
                                   row.stop, row.target) <= 0):
            raise ValueError("Invalid trade size or price")
        if ((row.side == 1 and not row.stop < row.entry_price < row.target)
                or (row.side == -1 and not row.target < row.entry_price < row.stop)):
            raise ValueError("Invalid protective stop/target geometry")
        gross = row.side * (row.exit_price - row.entry_price) * row.ounces
        if (abs(row.cost - 0.40 * row.ounces) > 1e-9
                or abs(row.gross_pnl - gross) > 1e-7
                or abs(row.net_pnl - (gross - row.cost)) > 1e-7):
            raise ValueError("Trade gross/net/fee arithmetic mismatch")
        stamps = [pd.Timestamp(value) for value in
                  (row.signal_at, row.entry_at, row.closed_at)]
        if (any(pd.isna(stamp) or stamp.tzinfo is None for stamp in stamps)
                or not stamps[0] <= stamps[1] <= stamps[2]):
            raise ValueError("Trade timestamps are not ordered timezone-aware UTC")
        if row.exit_reason in ("stop", "ambiguous_stop_first"):
            if abs(row.exit_price - row.stop) > 1e-7:
                raise ValueError("Trade stop exit differs from stop")
        elif row.exit_reason in ("target", "open_target"):
            if abs(row.exit_price - row.target) > 1e-7:
                raise ValueError("Trade target exit differs from target")
        elif row.exit_reason in ("open_stop", "gap_stop", "entry_open_beyond_stop"):
            if row.side * (row.exit_price - row.stop) > 1e-7:
                raise ValueError("Adverse open exit improved beyond stop")
        elif row.exit_reason != "end_of_data":
            raise ValueError("Unknown trade exit reason")


def _compare_outputs(reference: Path, fast: Path, *, identity: str) -> dict:
    """Fail on any differing execution field, report bucket, or M1 equity mark."""
    summaries = []
    for engine, directory in (("reference", reference), ("fast", fast)):
        summary, _ = _load_strict(directory / "summary.json")
        if type(summary) is not dict:
            raise ValueError("Invalid execution summary")
        params = summary.get("run_parameters", {})
        if (type(params) is not dict or params.get("execution") != engine
                or params.get("strategy") != "arithmetic"
                or params.get("timeframe") != "M1"
                or params.get("arithmetic_formula_sha256") != identity
                or params.get("all_in_cost_per_ounce") != 0.40
                or params.get("ounces") != 1.0):
            raise ValueError("Unexpected or mismatched canonical CLI parameters")
        if summary.get("source_fingerprints", {}).get("loaded_m1_bidask_sha256") is None:
            raise ValueError("Missing loaded M1 Bid/Ask fingerprint")
        if summary.get("months_with_m1_observations") != 12:
            raise ValueError("Annual training sample omits an observed calendar month")
        summaries.append(summary)
    if summaries[0]["source_fingerprints"] != summaries[1]["source_fingerprints"]:
        raise ValueError("Reference/Fast source fingerprints differ")
    for key in SUMMARY_KEYS:
        if summaries[0].get(key) != summaries[1].get(key):
            raise ValueError(f"Reference/Fast summary mismatch: {key}")
    for filename in REPORTS:
        left = pd.read_csv(reference / filename)
        right = pd.read_csv(fast / filename)
        if filename == "trades.csv":
            for frame in (left, right):
                if frame.columns.has_duplicates or not set(TRADE_FIELDS).issubset(frame.columns):
                    raise ValueError("Trade ledger missing 15 execution audit fields")
        try:
            pd.testing.assert_frame_equal(
                left, right, check_dtype=False, check_exact=False,
                atol=1e-7, rtol=0, check_like=False,
            )
        except AssertionError as exc:
            raise ValueError(f"Reference/Fast {filename} mismatch") from exc
    trades = pd.read_csv(reference / "trades.csv")
    summary = summaries[0]
    _verify_trade_accounting(trades)
    if summary["trades"] != len(trades):
        raise ValueError("Trade count differs from persisted ledger")
    if len(trades):
        for field in ("net_pnl", "cost", "ounces"):
            if not pd.to_numeric(trades[field], errors="coerce").notna().all():
                raise ValueError(f"Invalid trade accounting field: {field}")
        fees = (trades["ounces"] * 0.40).sum()
        if abs(float(trades["cost"].sum()) - float(fees)) > 1e-7:
            raise ValueError("Noncanonical per-trade fee")
        net = float(trades["net_pnl"].sum())
    else:
        fees = net = 0.0
    if (abs(float(summary["total_fees"]) - float(fees)) > 1e-7
            or abs(float(summary["net_pnl"]) - net) > 1e-7):
        raise ValueError("Trade/summary accounting mismatch")
    for filename in ("monthly.csv", "weekly.csv"):
        buckets = pd.read_csv(reference / filename)
        if abs(float(buckets["net_pnl"].sum()) - net) > 1e-7:
            raise ValueError(f"Trade/{filename} accounting mismatch")
    return {"trades": len(trades), "net_usd_per_oz": net,
            "fees_usd": float(fees), "positive_months": summary["positive_months"],
            "bidask_sha256": summaries[0]["source_fingerprints"]["loaded_m1_bidask_sha256"]}


def execute(training_input: Path, generation_manifest: Path,
            dispatch_dir: Path, data: Path, source_sha256: str,
            year: int, destination: Path, *, start_ordinal: int = 1,
            limit: int = 8) -> dict:
    """No holdout access: selected year must be in frozen TRAINING years."""
    if (type(year) is not int or type(start_ordinal) is not int
            or type(limit) is not int or start_ordinal < 1
            or not 1 <= limit <= 128 or type(source_sha256) is not str
            or SHA.fullmatch(source_sha256) is None):
        raise ValueError("Invalid bounded frozen training replay controls")
    if source_sha256 != SOURCE_SHA:
        raise ValueError("Only the preregistered original Gold ZIP SHA is permitted")
    _safe_destination(destination)
    if not data.is_file() or data.suffix.lower() != ".zip":
        raise ValueError("A local original source ZIP is required")
    if _digest(data) != source_sha256:
        raise ValueError("Original source ZIP SHA mismatch")
    # Replays generation from the ORIGINAL training input, never trusts an
    # isolated self-reported dispatch index or a changed formula JSON.
    dispatch = materialize(training_input, generation_manifest, dispatch_dir)
    if year not in dispatch["training_years"]:
        raise ValueError("Year is not in frozen training; holdout replay forbidden")
    entries = dispatch["formulas"]
    if start_ordinal > len(entries):
        raise ValueError("Requested ordinal exceeds frozen generation")
    selected = entries[start_ordinal - 1:start_ordinal - 1 + limit]
    for row in selected:
        _strict_formula(dispatch_dir / row["relative_path"], row)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _safe_destination(destination)
    staging = Path(tempfile.mkdtemp(prefix=".nrfx_arithmetic_training_",
                                    dir=destination.parent))
    try:
        records = []
        for row in selected:
            name = f"{row['ordinal']:03d}_{row['identity'][:16]}"
            formula_path = dispatch_dir / row["relative_path"]
            outputs = {}
            for engine in ("reference", "fast"):
                target = staging / name / engine
                command = [
                    sys.executable, "-m", "norisk_quant.cli", "backtest",
                    "--data", str(data), "--start", f"{year}-01-01",
                    "--end", f"{year}-12-31", "--out", str(target),
                    "--strategy", "arithmetic", "--timeframe", "M1",
                    "--formula-json", str(formula_path), "--execution", engine,
                    "--ounces", "1", "--all-in-cost-per-ounce", "0.40",
                ]
                subprocess.run(command, check=True, capture_output=True,
                               text=True)
                outputs[engine] = target
            metrics = _compare_outputs(outputs["reference"], outputs["fast"],
                                       identity=row["identity"])
            records.append({"ordinal": row["ordinal"], "identity": row["identity"],
                            "reference_fast_parity": "PASSED",
                            "metrics": metrics, "relative_dir": name})
        if _digest(data) != source_sha256:
            raise ValueError("Original source ZIP changed during replay")
        # Refuse to publish if source evidence or any formula changed mid-run.
        if materialize(training_input, generation_manifest, dispatch_dir) != dispatch:
            raise ValueError("Frozen dispatch changed during replay")
        for row in selected:
            _strict_formula(dispatch_dir / row["relative_path"], row)
        index = {
            "schema": SCHEMA, "training_only": True,
            "independent_oos_proven": False, "live_trading_authorized": False,
            "data_archive_sha256": source_sha256,
            "training_input_sha256": dispatch["training_input_sha256"],
            "generation_manifest_sha256": dispatch["generation_manifest_sha256"],
            "year": year, "requested_start_ordinal": start_ordinal,
            "requested_limit": limit, "completed": len(records),
            "all_in_cost_per_ounce": 0.40, "results": records,
        }
        (staging / "training_replay_index.json").write_text(
            json.dumps(index, sort_keys=True, indent=2, allow_nan=False) + "\n",
            encoding="utf-8")
        _safe_destination(destination)
        os.replace(staging, destination)
        return index
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("training-input", "generation-manifest", "dispatch-dir",
                 "data", "data-sha256", "year", "out"):
        parser.add_argument("--" + name, required=True,
                            type=int if name == "year" else
                            str if name == "data-sha256" else Path)
    parser.add_argument("--start-ordinal", type=int, default=1)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv)
    result = execute(args.training_input, args.generation_manifest,
                     args.dispatch_dir, args.data, args.data_sha256,
                     args.year, args.out, start_ordinal=args.start_ordinal,
                     limit=args.limit)
    print(json.dumps({"completed": result["completed"], "year": result["year"],
                      "status": "TRAINING_ONLY_PARITY_VERIFIED"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
