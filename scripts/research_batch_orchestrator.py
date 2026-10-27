"""Offline frozen batch research orchestration. No trading, broker access, or OOS claims."""
from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
from html import escape
from itertools import product
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

SCHEMA = "NRFX_FROZEN_BATCH_V1"
PASSED = "ACCOUNTING_RECONCILED_HISTORICAL_EXPOSED_NOT_OOS"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
JOB_ID = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")
STRATEGY_PARAMS = {
    "ema": {"fast", "slow", "stop_atr", "rr"},
    "donchian": {"donchian_lookback", "stop_usd", "target_usd"},
    "fvg": {"fvg_min_gap_usd", "fvg_stop_buffer_usd", "fvg_rr", "fvg_expiry_hours"},
    "bos-fib": {"bos_pivot_left", "bos_pivot_right", "bos_fib_entry",
                "bos_rr", "bos_stop_buffer_usd", "bos_min_break_usd",
                "bos_min_impulse_usd", "bos_expiry_minutes",
                "bos_min_gross_reward_fee_multiple"},
    "qs01": set(),
}
INT_PARAMS = {"fast", "slow", "donchian_lookback", "bos_pivot_left",
              "bos_pivot_right", "bos_expiry_minutes"}
BASE = {"strategy", "timeframe", "execution", "start", "end"}


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_spec(spec: object) -> dict:
    if not isinstance(spec, dict) or set(spec) != BASE | {"parameters"}:
        raise ValueError("Unexpected or missing strategy specification field")
    if type(spec["strategy"]) is not str or spec["strategy"] not in STRATEGY_PARAMS:
        raise ValueError("Unsupported research strategy")
    if spec["timeframe"] not in ("M1", "M5", "M15", "H1", "H4"):
        raise ValueError("Unsupported timeframe")
    if spec["execution"] not in ("fast", "reference"):
        raise ValueError("Unsupported execution")
    if spec["strategy"] in ("fvg", "bos-fib") and spec["execution"] != "reference":
        raise ValueError("Limit execution is reference-only")
    if spec["strategy"] in ("bos-fib", "qs01") and spec["timeframe"] != "M1":
        raise ValueError("Frozen strategy requires M1")
    for field in ("start", "end"):
        if type(spec[field]) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", spec[field]):
            raise ValueError("Invalid YYYY-MM-DD date")
        date.fromisoformat(spec[field])
    if spec["start"] > spec["end"]:
        raise ValueError("Chronologically reversed window")
    params = spec["parameters"]
    if not isinstance(params, dict) or not set(params).issubset(STRATEGY_PARAMS[spec["strategy"]]):
        raise ValueError("Unsupported strategy parameters")
    for name, value in params.items():
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Parameter must be a finite real number, not boolean")
        if name in INT_PARAMS and (type(value) is not int or value < 1):
            raise ValueError("Parameter requires positive integer")
        if name not in INT_PARAMS and value <= (0 if name != "bos_min_gross_reward_fee_multiple" else -1):
            raise ValueError("Parameter must be nonnegative or positive")
    if spec["strategy"] == "ema" and params.get("fast", 9) >= params.get("slow", 21):
        raise ValueError("EMA fast must be below slow")
    if spec["strategy"] == "bos-fib" and params.get("bos_fib_entry", 0.618) >= 1:
        raise ValueError("Fibonacci entry fraction must be below 1")
    return spec


def expand(plan: dict, *, limit: int = 50000) -> tuple[list[dict], str]:
    if not isinstance(plan, dict) or set(plan) != {
        "schema", "dataset", "source_sha256", "engine_commit",
        "exposure_context", "jobs", "grids",
    }:
        raise ValueError("Unexpected frozen plan schema")
    if plan["schema"] != SCHEMA or plan["exposure_context"] != "historical_exposed":
        raise ValueError("Historical exposed research only")
    if type(plan["dataset"]) is not str or not Path(plan["dataset"]).is_absolute():
        raise ValueError("Dataset must be an absolute private local file")
    if type(plan["source_sha256"]) is not str or not HEX64.fullmatch(plan["source_sha256"]):
        raise ValueError("Original data SHA256 required")
    if type(plan["engine_commit"]) is not str or not HEX40.fullmatch(plan["engine_commit"]):
        raise ValueError("Full Git commit required")
    if not isinstance(plan["jobs"], list) or not isinstance(plan["grids"], list):
        raise ValueError("Jobs and grids must be arrays")
    if type(limit) is not int or not 1 <= limit <= 50000:
        raise ValueError("Invalid limit")
    jobs = []
    ids = set()

    def add(ident: str, spec: dict):
        if type(ident) is not str or not JOB_ID.fullmatch(ident):
            raise ValueError("Unsafe job ID")
        if ident in ids or len(jobs) >= limit:
            raise ValueError("Duplicate ID or batch expansion cap reached")
        ids.add(ident)
        jobs.append({"id": ident, "spec": check_spec(spec)})

    for item in plan["jobs"]:
        if not isinstance(item, dict) or set(item) != BASE | {"parameters", "id"}:
            raise ValueError("Invalid individual experiment")
        add(item["id"], {k: item[k] for k in BASE | {"parameters"}})
    for grid in plan["grids"]:
        if not isinstance(grid, dict) or set(grid) != BASE | {"grid", "id_prefix"}:
            raise ValueError("Invalid frozen parameter grid")
        dimensions = grid["grid"]
        if (type(grid["strategy"]) is not str
                or grid["strategy"] not in STRATEGY_PARAMS
                or not isinstance(dimensions, dict) or not dimensions
                or not set(dimensions).issubset(STRATEGY_PARAMS[grid["strategy"]])):
            raise ValueError("Unsupported grid dimensions")
        keys = sorted(dimensions)
        values = []
        count = 1
        for key in keys:
            arr = dimensions[key]
            if not isinstance(arr, list) or not arr:
                raise ValueError("Empty grid axis")
            count *= len(arr)
            if len(jobs) + count > limit:
                raise ValueError("Grid exceeds expansion cap")
            values.append(arr)
        for combination in product(*values):
            spec = {k: grid[k] for k in BASE}
            spec["parameters"] = dict(zip(keys, combination))
            check_spec(spec)
            suffix = hashlib.sha256(canonical(spec)).hexdigest()[:12]
            add(grid["id_prefix"] + "-" + suffix, spec)
    if not jobs:
        raise ValueError("Empty frozen research plan")
    return jobs, hashlib.sha256(canonical(plan)).hexdigest()


def expected_months(first: str, last: str) -> list[str]:
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    year, month = a.year, a.month
    result = []
    while (year, month) <= (b.year, b.month):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return result


def finite(value: object, *, nonnegative: bool = False) -> float:
    if type(value) not in (int, float, str):
        raise ValueError("Invalid report numeric field")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Malformed numeric value") from exc
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ValueError("Nonfinite or negative report value")
    return result


def count(value: object) -> int:
    if type(value) is int and value >= 0:
        return value
    if type(value) is str and re.fullmatch(r"(?:0|[1-9]\d*)", value):
        return int(value)
    raise ValueError("Invalid nonnegative integer report field")


def same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


def audit_run(folder: Path, spec: dict, source_sha: str, engine_sha: str) -> dict:
    """Reconcile actual engine output without certifying broker execution."""
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    with (folder / "monthly.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not isinstance(summary, dict) or not rows:
        raise ValueError("Missing evidence")
    if summary.get("execution") != "synthetic_same_reference_bid_ohlc_fixed_all_in_fee":
        raise ValueError("Unknown execution mode")
    settings = summary.get("settings")
    if not isinstance(settings, dict) or not same(
        finite(settings.get("roundtrip_cost_per_ounce")), 0.40
    ):
        raise ValueError("Research transaction cost mismatch")
    provenance = summary.get("source_fingerprints")
    if (not isinstance(provenance, dict)
            or provenance.get("source_file_sha256") != source_sha
            or provenance.get("git_revision_env") != engine_sha
            or type(provenance.get("loaded_m1_bidask_sha256")) is not str
            or not HEX64.fullmatch(provenance["loaded_m1_bidask_sha256"])):
        raise ValueError("Source/code/M1 fingerprint mismatch")
    actual = summary.get("run_parameters")
    if not isinstance(actual, dict):
        raise ValueError("No recorded CLI parameters")
    for field in BASE:
        if actual.get(field) != spec[field]:
            raise ValueError(f"Recorded run setting differs: {field}")
    for key, value in spec["parameters"].items():
        if actual.get(key) != value:
            raise ValueError(f"Recorded strategy setting differs: {key}")
    months = expected_months(spec["start"], spec["end"])
    if [row.get("period") for row in rows] != months:
        raise ValueError("Monthly rows do not fully cover requested interval")
    pnl, trades, fees, gaps, forced = {}, 0, 0.0, 0, 0
    for row in rows:
        if count(row.get("observed_m1_samples")) == 0:
            raise ValueError("Calendar month without observed M1 cannot be certified")
        pnl[row["period"]] = finite(row.get("net_pnl"))
        trades += count(row.get("trades"))
        fees += finite(row.get("total_cost"), nonnegative=True)
        gaps += count(row.get("uncertain_gap_trades"))
        forced += count(row.get("synthetic_end_of_data_trades"))
    if (count(summary.get("trades")) != trades
            or not same(finite(summary.get("net_pnl")), sum(pnl.values()))
            or not same(finite(summary.get("total_fees")), fees)
            or count(summary.get("months_observed")) != len(months)
            or count(summary.get("positive_months")) != sum(v > 0 for v in pnl.values())
            or count(summary.get("nonpositive_months")) != sum(v <= 0 for v in pnl.values())
            or count(summary.get("forced_end_of_data_closures")) != forced):
        raise ValueError("Monthly and summary accounting disagree")
    return {
        "status": PASSED, "trades": trades, "net_pnl": round(sum(pnl.values()), 8),
        "total_cost": round(fees, 8), "positive_months": sum(v > 0 for v in pnl.values()),
        "months_observed": len(months), "monthly_net_pnl": pnl,
        "uncertain_gap_trade_month_assignments": gaps,
        "synthetic_end_of_data_closures": forced,
        "summary_sha256": file_sha(folder / "summary.json"),
        "monthly_sha256": file_sha(folder / "monthly.csv"),
    }


def checkout_commit() -> str:
    try:
        result = subprocess.run([
            "git", "-C", str(Path(__file__).resolve().parents[1]), "rev-parse", "HEAD"
        ], check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise ValueError("Git revision unavailable") from exc
    if not HEX40.fullmatch(result):
        raise ValueError("Invalid Git revision")
    return result


def atomic_manifest(path: Path, data: dict) -> None:
    staging = path.with_name(path.name + ".tmp")
    staging.write_bytes(canonical(data) + b"\n")
    os.replace(staging, path)


def render_index(manifest: dict) -> str:
    months = sorted({m for rec in manifest["results"].values()
                     if rec.get("status") == PASSED for m in rec["monthly_net_pnl"]})
    heads = "".join("<th>" + escape(m) + "</th>" for m in months)
    body = []
    for name, rec in sorted(manifest["results"].items()):
        cells = []
        for month in months:
            value = rec.get("monthly_net_pnl", {}).get(month)
            if value is None:
                cells.append("<td>—</td>")
            else:
                color = "gain" if value > 0 else "loss" if value < 0 else ""
                cells.append('<td class="' + color + '">' + f"{value:+,.2f}" + "</td>")
        links = "—"
        if rec.get("status") == PASSED:
            links = (f'<a href="runs/{name}/monthly.csv">monthly</a> · '
                     f'<a href="runs/{name}/weekly.csv">weekly</a> · '
                     f'<a href="runs/{name}/summary.json">audit</a>')
        body.append("<tr><th>" + escape(name) + "</th><td>"
                    + escape(rec["status"]) + "</td><td>" + links + "</td>"
                    + "".join(cells) + "</tr>")
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>No Risk FX | Historical Quant Research</title>'
            '<style>:root{color-scheme:dark;font-family:system-ui;background:#071526;color:#eaf0fb}'
            'body{padding:clamp(14px,3vw,42px)}h1{color:#e2c184}'
            'p{line-height:1.6;color:#c0cad8;max-width:1000px}'
            '.wrap{overflow:auto;border:1px solid #334761;border-radius:12px}'
            'table{border-collapse:collapse;width:100%;white-space:nowrap}'
            'th,td{padding:12px;text-align:right;border-bottom:1px solid #273b50}'
            'th:first-child{text-align:left}.gain{color:#8cdfbb}'
            '.loss{color:#f3aaaa}a{color:#b6dcff}</style></head><body>'
            '<h1>NO RISK FX · Monthly Research Evidence</h1>'
            '<p>Local historical-exposed research only, NOT independent OOS or broker fills. '
            'P/L is net for 1 oz synthetic XAUUSD position with 0.40 USD/oz '
            'all-in roundtrip costs. Forced end-of-data trades and gap exposures '
            'require inspection. Every accepted row is reconciled to engine reports.</p>'
            '<div class="wrap"><table><thead><tr><th>Research job</th><th>Status</th>'
            '<th>Reports</th>' + heads + '</tr></thead><tbody>'
            + "".join(body) + '</tbody></table></div></body></html>')


def run_plan(plan: dict, output: Path, *, max_jobs: int = 20, dry_run: bool = False) -> dict:
    jobs, plan_sha = expand(plan)
    if type(max_jobs) is not int or not 1 <= max_jobs <= 500:
        raise ValueError("Per-invocation job cap is 1..500")
    if dry_run:
        return {"status": "DEFINED_ONLY_NO_BACKTEST", "jobs": len(jobs),
                "plan_sha256": plan_sha, "budget": max_jobs}
    dataset = Path(plan["dataset"]).resolve(strict=True)
    if not dataset.is_file() or file_sha(dataset) != plan["source_sha256"]:
        raise ValueError("Original private source archive SHA256 mismatch")
    revision = checkout_commit()
    if revision != plan["engine_commit"]:
        raise ValueError("Current checkout differs from frozen engine revision")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "batch_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (not isinstance(manifest, dict)
                or set(manifest) != {"schema", "plan_sha256", "source_sha256", "engine_commit", "results"}
                or manifest["schema"] != SCHEMA
                or manifest["plan_sha256"] != plan_sha
                or manifest["source_sha256"] != plan["source_sha256"]
                or manifest["engine_commit"] != revision
                or not isinstance(manifest["results"], dict)):
            raise ValueError("Existing output has incompatible plan/commit")
    else:
        manifest = {"schema": SCHEMA, "plan_sha256": plan_sha,
                    "source_sha256": plan["source_sha256"],
                    "engine_commit": revision, "results": {}}
    launched = 0
    for job in jobs:
        ident, spec = job["id"], job["spec"]
        folder = output / "runs" / ident
        existing = manifest["results"].get(ident)
        if existing is not None:
            if existing.get("status") != PASSED:
                raise ValueError("A failed run requires manual investigation")
            if audit_run(folder, spec, plan["source_sha256"], revision) != existing:
                raise ValueError("Previously accepted evidence was modified")
            continue
        if launched >= max_jobs:
            break
        if folder.exists() and any(folder.iterdir()):
            raise ValueError("Unknown existing run output requires inspection")
        folder.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-m", "norisk_quant.cli", "backtest",
               "--data", str(dataset), "--start", spec["start"], "--end", spec["end"],
               "--out", str(folder), "--strategy", spec["strategy"],
               "--timeframe", spec["timeframe"], "--execution", spec["execution"],
               "--ounces", "1", "--all-in-cost-per-ounce", "0.40"]
        for key, value in sorted(spec["parameters"].items()):
            cmd += ["--" + key.replace("_", "-"), str(value)]
        env = dict(os.environ, GITHUB_SHA=revision)
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True,
                           timeout=7200, env=env)
            record = audit_run(folder, spec, plan["source_sha256"], revision)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError,
                ValueError, FileNotFoundError, KeyError) as exc:
            manifest["results"][ident] = {
                "status": "FAILED_REQUIRES_INVESTIGATION", "error_type": type(exc).__name__
            }
            atomic_manifest(manifest_path, manifest)
            raise RuntimeError("A backtest failed verification: " + ident) from exc
        manifest["results"][ident] = record
        atomic_manifest(manifest_path, manifest)
        launched += 1
    index = output / "research_batch_index.html"
    index.write_text(render_index(manifest), encoding="utf-8")
    return {
        "status": "HISTORICAL_RESEARCH_ONLY", "defined_jobs": len(jobs),
        "reconciled_jobs": sum(
            rec.get("status") == PASSED for rec in manifest["results"].values()),
        "executed_this_invocation": launched, "plan_sha256": plan_sha,
        "index": str(index),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-jobs", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    print(json.dumps(run_plan(plan, args.out, max_jobs=args.max_jobs,
                              dry_run=args.dry_run), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
