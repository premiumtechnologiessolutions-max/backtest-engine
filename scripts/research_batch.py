"""Offline, opt-in, reproducible XAUUSD batch runner using canonical NRFX CLI.

Screens only existing EMA/Donchian signal variants. No external/vectorbt fills,
private-data uploads, live trading or independent OOS certification.
"""
from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
PARAMS = {
    "ema": {"fast": ("int", 1, 200), "slow": ("int", 2, 400),
            "stop_atr": ("float", 0.01, 100.0), "rr": ("float", 0.1, 100.0)},
    "donchian": {"donchian_lookback": ("int", 2, 500),
                 "stop_usd": ("float", 0.01, 1000.0),
                 "target_usd": ("float", 0.01, 2000.0)},
}
FLAGS = {"donchian_lookback": "--donchian-lookback", "fast": "--fast",
         "slow": "--slow", "stop_atr": "--stop-atr", "rr": "--rr",
         "stop_usd": "--stop-usd", "target_usd": "--target-usd"}
MAX_EXPERIMENTS = 50


class ResearchBatchError(ValueError):
    """A plan or report failed an auditable, fail-closed contract."""


def _date(value: object, key: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ResearchBatchError(f"{key}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ResearchBatchError(f"{key}: invalid calendar day") from exc


def _strict_number(value: object, typ: str, low: float, high: float, label: str) -> None:
    valid = type(value) is int if typ == "int" else type(value) in (int, float)
    if not valid or not math.isfinite(value) or not low <= value <= high:
        raise ResearchBatchError(f"{label}: expected finite {typ} in [{low}, {high}]")


def validate_plan(obj: object) -> dict:
    if not isinstance(obj, dict) or set(obj) != {
        "schema", "source", "source_sha256", "engine_commit", "start", "end", "experiments"
    }:
        raise ResearchBatchError("Plan requires the exact NRFX_BATCH_V1 schema")
    if obj["schema"] != "NRFX_BATCH_V1":
        raise ResearchBatchError("Unsupported batch schema")
    if (not isinstance(obj["source"], str) or not obj["source"].strip()
            or not Path(obj["source"]).is_absolute()):
        raise ResearchBatchError("Absolute local source path required")
    if not isinstance(obj["source_sha256"], str) or not HEX64.fullmatch(obj["source_sha256"]):
        raise ResearchBatchError("Full lowercase source SHA256 required")
    if not isinstance(obj["engine_commit"], str) or not HEX40.fullmatch(obj["engine_commit"]):
        raise ResearchBatchError("Full lowercase immutable engine Git commit required")
    start = _date(obj["start"], "start")
    end = _date(obj["end"], "end")
    if start > end:
        raise ResearchBatchError("start must be <= end")
    specs = obj["experiments"]
    if not isinstance(specs, list) or not 1 <= len(specs) <= MAX_EXPERIMENTS:
        raise ResearchBatchError(f"1..{MAX_EXPERIMENTS} explicit experiments required")
    ids: set[str] = set()
    for spec in specs:
        if not isinstance(spec, dict) or set(spec) != {
            "id", "strategy", "timeframe", "execution", "parameters"
        }:
            raise ResearchBatchError("Unexpected experiment fields")
        name = spec["id"]
        if not isinstance(name, str) or not IDENTIFIER.fullmatch(name) or name in ids:
            raise ResearchBatchError("Experiment IDs must be safe and unique")
        ids.add(name)
        strategy = spec["strategy"]
        if strategy not in PARAMS:
            raise ResearchBatchError(f"Unsupported research strategy: {strategy}")
        if spec["timeframe"] not in ("M1", "M5", "M15", "H1", "H4"):
            raise ResearchBatchError("Unsupported timeframe")
        if spec["execution"] not in ("reference", "fast"):
            raise ResearchBatchError("Unsupported execution mode")
        params = spec["parameters"]
        if not isinstance(params, dict) or set(params) != set(PARAMS[strategy]):
            raise ResearchBatchError(f"{name}: parameters must exactly match {strategy} spec")
        for field, (kind, lo, hi) in PARAMS[strategy].items():
            _strict_number(params[field], kind, lo, hi, f"{name}.{field}")
        if strategy == "ema" and not params["fast"] < params["slow"]:
            raise ResearchBatchError("EMA fast must be strictly less than slow")
    return obj


def fingerprint_file(source: Path) -> str:
    if not source.is_file():
        raise ResearchBatchError("Only local file sources supported in v1; source stays private")
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checkout(required_sha: str, root: Path = ROOT) -> None:
    """Do not claim reproducibility on a different or modified checkout."""
    try:
        actual = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                capture_output=True, text=True, timeout=20,
                                check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                               cwd=root, capture_output=True, text=True, timeout=20,
                               check=True).stdout.strip()
    except (subprocess.SubprocessError, OSError) as exc:
        raise ResearchBatchError("Cannot verify immutable local engine checkout") from exc
    if actual != required_sha or dirty:
        raise ResearchBatchError(
            "Current code differs from frozen engine commit or has tracked modifications"
        )


def make_command(spec: dict, plan: dict, out: Path) -> list[str]:
    command = [
        sys.executable, "-m", "norisk_quant.cli", "backtest",
        "--data", plan["source"], "--start", plan["start"], "--end", plan["end"],
        "--out", str(out), "--strategy", spec["strategy"], "--timeframe",
        spec["timeframe"], "--execution", spec["execution"], "--ounces", "1",
        "--all-in-cost-per-ounce", "0.40",
    ]
    for key, value in sorted(spec["parameters"].items()):
        command.extend([FLAGS[key], str(value)])
    return command


def _month_range(start: date, end: date) -> list[str]:
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


def _finite_float(value: Any, label: str) -> float:
    if type(value) not in (str, int, float):
        raise ResearchBatchError(f"{label}: nonnumeric value")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResearchBatchError(f"{label}: invalid number") from exc
    if not math.isfinite(number):
        raise ResearchBatchError(f"{label}: nonfinite number")
    return number


def _int_value(value: Any, label: str) -> int:
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value):
        number = int(value)
    else:
        raise ResearchBatchError(f"{label}: must be a nonnegative integer")
    if number < 0:
        raise ResearchBatchError(f"{label}: must be nonnegative")
    return number


def _observed(value: str) -> bool:
    if value not in ("True", "False", "true", "false"):
        raise ResearchBatchError("month_has_observed_m1 must be explicit boolean")
    return value.lower() == "true"


def parse_report(out: Path, plan: dict, spec: dict) -> dict:
    """Reconcile exported calendar-month P/L to the canonical engine summary."""
    summary_path, month_path = out / "summary.json", out / "monthly.csv"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        with month_path.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            required = {
                "period", "net_pnl", "trades", "month_has_observed_m1",
                "uncertain_gap_trades", "synthetic_end_of_data_trades",
            }
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ResearchBatchError("Monthly report has duplicate/missing headings")
            if not required.issubset(reader.fieldnames):
                raise ResearchBatchError("Monthly report lacks required accounting fields")
            rows = list(reader)
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
        raise ResearchBatchError("Missing/invalid canonical backtest outputs") from exc
    if not isinstance(summary, dict):
        raise ResearchBatchError("Invalid canonical summary")
    if summary.get("execution") != "synthetic_same_reference_bid_ohlc_fixed_all_in_fee":
        raise ResearchBatchError("Unexpected execution provenance")
    params = summary.get("run_parameters")
    expected_args = {"strategy": spec["strategy"], "timeframe": spec["timeframe"],
                     "execution": spec["execution"], "ounces": 1.0,
                     "all_in_cost_per_ounce": 0.40}
    if not isinstance(params, dict) or any(params.get(k) != v for k, v in expected_args.items()):
        raise ResearchBatchError("Canonical engine reported wrong run parameters")
    source_fps = summary.get("source_fingerprints")
    if not isinstance(source_fps, dict) or source_fps.get("source_file_sha256") != plan["source_sha256"]:
        raise ResearchBatchError("Engine source fingerprint differs from frozen plan")
    if source_fps.get("git_revision_env") != plan["engine_commit"]:
        raise ResearchBatchError("Engine version fingerprint differs from frozen plan")
    for key, value in spec["parameters"].items():
        if params.get(key) != value:
            raise ResearchBatchError(f"Mismatch in engine parameter: {key}")
    start, end = _date(plan["start"], "start"), _date(plan["end"], "end")
    expected = _month_range(start, end)
    seen, periods = [], []
    running_net, running_trades = 0.0, 0
    for record in rows:
        month = record["period"]
        if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise ResearchBatchError("Invalid monthly period")
        seen.append(month)
        profit = _finite_float(record["net_pnl"], "monthly.net_pnl")
        trades = _int_value(record["trades"], "monthly.trades")
        gaps = _int_value(record["uncertain_gap_trades"], "monthly.uncertain_gap_trades")
        forced = _int_value(record["synthetic_end_of_data_trades"],
                            "monthly.synthetic_end_of_data_trades")
        if gaps > trades or forced > trades:
            raise ResearchBatchError("Gap/forced counts exceed trade counts")
        observed = _observed(record["month_has_observed_m1"])
        if not observed and (trades or profit):
            raise ResearchBatchError("Booked trading in month without observed M1")
        yy, mm = map(int, month.split("-"))
        full = (date(yy, mm, 1) >= start and
                date(yy, mm, calendar.monthrange(yy, mm)[1]) <= end)
        periods.append({
            "period": month, "net_pnl": profit, "trades": trades,
            "has_m1": observed, "full_requested_month": full,
            "uncertain_gap_trades": gaps, "synthetic_end_of_data_trades": forced,
            "positive_full_observed_month": bool(full and observed and profit > 0),
        })
        running_net += profit
        running_trades += trades
    if seen != expected:
        raise ResearchBatchError("Monthly rows incomplete, repeated or out of order")
    net = _finite_float(summary.get("net_pnl"), "summary.net_pnl")
    summary_trades = _int_value(summary.get("trades"), "summary.trades")
    if (not math.isclose(running_net, net, abs_tol=1e-6, rel_tol=1e-10)
            or running_trades != summary_trades):
        raise ResearchBatchError("Monthly accounting does not reconcile to summary")
    if _int_value(summary.get("months_observed"), "summary.months_observed") != len(periods):
        raise ResearchBatchError("Summary monthly count mismatch")
    return {
        "net_pnl_usd_per_oz": net, "trades": summary_trades,
        "positive_full_observed_months":
            sum(p["positive_full_observed_month"] for p in periods),
        "eligible_full_observed_months":
            sum(p["full_requested_month"] and p["has_m1"] for p in periods),
        "months": periods,
        "summary_sha256": fingerprint_file(summary_path),
        "monthly_sha256": fingerprint_file(month_path),
        "status": "REPLAYED_HISTORICALLY_EXPOSED_NOT_OOS",
    }


def _json_file(dest: Path, data: dict) -> None:
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False),
                   encoding="utf-8")
    tmp.replace(dest)


def execute_plan(plan: dict, out: Path, *, execute: bool = False) -> dict:
    validate_plan(plan)
    if not execute:
        return {
            "status": "PLAN_VALIDATED_ONLY_NO_BACKTEST_EXECUTED",
            "experiments": len(plan["experiments"]),
            "commands": [make_command(spec, plan, out / spec["id"])
                         for spec in plan["experiments"]],
        }
    source = Path(plan["source"])
    if fingerprint_file(source) != plan["source_sha256"]:
        raise ResearchBatchError("Original source archive SHA256 mismatch")
    verify_checkout(plan["engine_commit"])
    if out.exists():
        raise ResearchBatchError("Output directory already exists: refuse overwrite")
    out.mkdir(parents=True)
    manifest = {
        "schema": "NRFX_BATCH_RUN_V1", "status": "RUNNING_NOT_VERIFIED",
        "source_sha256": plan["source_sha256"], "engine_commit": plan["engine_commit"],
        "start": plan["start"], "end": plan["end"],
        "all_in_roundtrip_cost_usd_per_oz": 0.40,
        "research_label": "HISTORICALLY_EXPOSED_NOT_CLEAN_OOS",
        "monthly_scope_warning": (
            "full_requested_month means the requested date window includes that "
            "calendar month; it does NOT verify all broker M1 quotes existed. "
            "has_m1 confirms only some observed M1. Missing quotes, gaps, "
            "partial sessions, forced exits and floating equity need separate audits."
        ),
        "experiments": [],
    }
    _json_file(out / "batch_manifest.json", manifest)
    for spec in plan["experiments"]:
        destination = out / spec["id"]
        destination.mkdir()
        entry = {"id": spec["id"], "strategy": spec["strategy"],
                 "status": "RUNNING_NOT_VERIFIED"}
        manifest["experiments"].append(entry)
        _json_file(out / "batch_manifest.json", manifest)
        command = make_command(spec, plan, destination)
        try:
            env = os.environ.copy()
            env["GITHUB_SHA"] = plan["engine_commit"]
            process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                     text=True, timeout=3600, check=False)
            if process.returncode != 0:
                raise ResearchBatchError(f"Canonical CLI failed (exit {process.returncode})")
            if fingerprint_file(source) != plan["source_sha256"]:
                raise ResearchBatchError("Original source changed during execution")
            result = parse_report(destination, plan, spec)
            entry.update(result)
        except (ResearchBatchError, OSError, subprocess.SubprocessError) as exc:
            entry["status"] = "FAILED_NO_RESULTS_TRUSTED"
            entry["error"] = str(exc)
            manifest["status"] = "FAILED_NO_RANKING_PUBLISHED"
            _json_file(out / "batch_manifest.json", manifest)
            raise ResearchBatchError(
                f"Experiment {spec['id']} failed; inspect batch_manifest.json"
            ) from exc
        _json_file(out / "batch_manifest.json", manifest)
    manifest["status"] = "COMPLETE_CANONICAL_REPLAY_NOT_INDEPENDENT_OOS"
    _json_file(out / "batch_manifest.json", manifest)
    with (out / "monthly_comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "experiment", "month", "net_pnl_usd_per_oz", "trades", "has_m1",
            "full_requested_month", "gap_uncertain_trades",
            "synthetic_end_closures", "positive_full_observed_month",
        ])
        for entry in manifest["experiments"]:
            for month in entry["months"]:
                writer.writerow([
                    entry["id"], month["period"], month["net_pnl"], month["trades"],
                    month["has_m1"], month["full_requested_month"],
                    month["uncertain_gap_trades"],
                    month["synthetic_end_of_data_trades"],
                    month["positive_full_observed_month"],
                ])
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Actually replay frozen candidates (off by default)")
    args = parser.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = execute_plan(plan, args.out, execute=args.execute)
    print(json.dumps({k: v for k, v in result.items() if k != "commands"}, indent=2))
    if not args.execute:
        for command in result["commands"]:
            print("Command argv (not executed):", json.dumps(command))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
