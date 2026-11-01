"""Bootstrap a REAL, fully reconciled arithmetic-training campaign seed.

Runs the canonical reference and fast engines on the authorized private Gold
archive. Publishes an immutable initial_training_input.json only after every
annual report passes execution, accounting and BID/ASK parity audits.

Historical exposed TRAINING ONLY; no broker ticks, prospective OOS, live
trades or profitability guarantee. Keep the output outside any Git checkout.

Example:
 python -m scripts.bootstrap_arithmetic_training \
   --gold-zip "/private/Gold data.zip" --out "/private/quant_seed" \
   --years 2012 2013
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import json
import os
import shutil
import tempfile
import subprocess
import sys

import pandas as pd

from norisk_quant.math_discovery import Formula
from norisk_quant.research_training_integrity import training_summary
from scripts.materialize_arithmetic_generation import (
    _encoded, _load_strict, _publish_once,
)
from scripts.research_batch_orchestrator import exclusive_batch_lock
from scripts.run_arithmetic_dispatch_training import (
    SOURCE_SHA, _digest, _compare_outputs,
)
from scripts.run_arithmetic_research_cycles import _outside_checkout

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "NRFX_ARITHMETIC_TRAINING_INPUT_V1"


def _validate_years(years: list[int]) -> None:
    if (type(years) is not list or not 2 <= len(years) <= 8
            or any(type(y) is not int or not 2010 <= y <= 2026 for y in years)
            or years != sorted(set(years))):
        raise ValueError("Select 2..8 sorted distinct historical integer years, 2010..2026")


def _safe_root(root: Path, source: Path) -> None:
    if (any(p.is_symlink() for p in (root, *root.parents))
            or (root.exists() and not root.is_dir())):
        raise ValueError("Unsafe bootstrap output directory or ancestor")
    _outside_checkout(root.resolve())
    if source.resolve().is_relative_to(root.resolve()):
        raise ValueError("Private Gold archive cannot be inside bootstrap outputs")


def _run_engine(source: Path, year: int, formula_path: Path,
                execution: str, output: Path, timeout_seconds: int) -> None:
    """Publish only a complete CLI replay, never a partially written directory.

    The CLI writes to a private sibling staging folder. After success and
    structural checks, an atomic same-filesystem rename makes it visible.
    A process killed during the CLI may leave an orphan *staging* directory,
    which is never treated as a completed annual report on resume.
    """
    if execution not in ("reference", "fast"):
        raise ValueError("Unsupported research execution")
    if output.is_symlink() or output.exists():
        if output.is_symlink() or not output.is_dir():
            raise ValueError("Unsafe pre-existing annual report")
        # _annual_record independently audits the pair before seed publication.
        return
    stage = Path(tempfile.mkdtemp(prefix=f".{execution}.staging-",
                                  dir=output.parent))
    try:
        command = [
            sys.executable, "-m", "norisk_quant.cli", "backtest",
            "--data", str(source), "--start", f"{year}-01-01",
            "--end", f"{year}-12-31", "--out", str(stage),
            "--strategy", "arithmetic", "--timeframe", "M1",
            "--formula-json", str(formula_path), "--execution", execution,
            "--ounces", "1", "--all-in-cost-per-ounce", "0.40",
        ]
        try:
            completed = subprocess.run(
                command, cwd=REPO_ROOT, text=True, capture_output=True,
                timeout=timeout_seconds, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("Annual source replay failed or timed out") from exc
        if completed.returncode != 0:
            raise RuntimeError(
                f"Canonical {year} {execution} replay failed; "
                "no annual evidence was published"
            )
        for filename in ("summary.json", "trades.csv", "monthly.csv",
                         "weekly.csv", "equity_m1.csv", "gap_catalogue.csv"):
            path = stage / filename
            if path.is_symlink() or not path.is_file():
                raise ValueError("Canonical engine replay lacks required evidence")
        if output.exists() or output.is_symlink():
            raise FileExistsError("Concurrent annual evidence publication refused")
        os.rename(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _annual_record(folder: Path, formula: Formula, year: int) -> dict:
    reference, fast = folder / "reference", folder / "fast"
    for directory in (reference, fast):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Missing or symlinked annual engine evidence")
    verified = _compare_outputs(
        reference, fast, identity=formula.identity(), year=year)
    summary, _ = _load_strict(reference / "summary.json")
    fingerprints = summary.get("source_fingerprints")
    if (type(fingerprints) is not dict
            or fingerprints.get("source_file_sha256") != SOURCE_SHA
            or fingerprints.get("loaded_m1_bidask_sha256") != verified["bidask_sha256"]):
        raise ValueError("Verified annual report lacks original source fingerprint")
    monthly = pd.read_csv(reference / "monthly.csv")
    expected = [f"{year}-{m:02d}" for m in range(1, 13)]
    if (monthly.columns.has_duplicates or
            monthly["period"].tolist() != expected):
        raise ValueError("Training seed requires 12 consecutive UTC months")
    months = {period: float(pnl) for period, pnl in
              zip(expected, monthly["net_pnl"].tolist())}
    metrics = {
        "months": months, "trades": verified["trades"],
        "net_usd_per_oz": verified["net_usd_per_oz"],
        "fees_usd": verified["fees_usd"],
        "positive_months": verified["positive_months"],
        "uncertain_gap_trades": summary["trades_exposed_to_uncertain_gaps"],
        "synthetic_forced_closures": summary["forced_end_of_data_closures"],
        "accounting": "PASSED",
    }
    return {"year": year, "metrics": metrics}


def bootstrap(gold_zip: Path, root: Path, *,
              years: list[int] | None = None,
              timeout_seconds: int = 1200,
              min_free_gb: int = 1) -> dict:
    years = [2012, 2013] if years is None else years
    _validate_years(years)
    if (type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 3600
            or type(min_free_gb) is not int or not 0 <= min_free_gb <= 128):
        raise ValueError("Invalid finite bootstrap resource budget")
    gold_zip, root = Path(gold_zip), Path(root)
    if (gold_zip.is_symlink() or not gold_zip.is_file()
            or gold_zip.suffix.lower() != ".zip"
            or _digest(gold_zip) != SOURCE_SHA):
        raise ValueError("Only the SHA-pinned original private Gold ZIP is accepted")
    # The engine subprocess runs from REPO_ROOT; bind user-supplied relative
    # paths to their original invoking directory BEFORE changing its cwd.
    _safe_root(root, gold_zip)
    gold_zip, root = gold_zip.resolve(strict=True), root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    formula = Formula()
    with exclusive_batch_lock(root):
        # The formula is a declared baseline, not an observed market edge.
        formula_path = root / "baseline_formula.json"
        _publish_once(formula_path, _encoded(asdict(formula)))
        records = []
        for year in years:
            if shutil.disk_usage(root).free < min_free_gb * 1024 ** 3:
                raise ValueError("Insufficient private research disk budget")
            folder = root / "annual_replays" / str(year)
            if folder.is_symlink():
                raise ValueError("Unsafe annual replay directory")
            folder.mkdir(parents=True, exist_ok=True)
            for execution in ("reference", "fast"):
                _run_engine(gold_zip, year, formula_path, execution,
                            folder / execution, timeout_seconds)
            records.append(_annual_record(folder, formula, year))
        if _digest(gold_zip) != SOURCE_SHA:
            raise ValueError("Original private archive mutated during bootstrap")
        summary = training_summary(records, tuple(years))
        payload = {"schema": SCHEMA, "years": years, "explored_ids": [],
                   "candidates": [{"formula": asdict(formula), "records": records}]}
        output = root / "initial_training_input.json"
        _publish_once(output, _encoded(payload))
        return {
            "status": "REAL_SOURCE_TRAINING_SEED_RECONCILED_NOT_OOS",
            "seed": str(output), "years": years,
            "formula_identity": formula.identity(),
            "candidate_count": 1, "annual_reference_fast_pairs": len(years),
            "training_screen": summary["screen"],
            "net_usd_per_oz_training": summary["net_usd_per_oz"],
            "positive_months_training": summary["positive_months"],
            "total_months_training": summary["total_months"],
            "source_sha256": SOURCE_SHA,
            "independent_oos_proven": False,
            "live_trading_authorized": False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--years", nargs="+", type=int, default=[2012, 2013])
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--min-free-gb", type=int, default=1)
    args = parser.parse_args(argv)
    result = bootstrap(args.gold_zip, args.out, years=args.years,
                       timeout_seconds=args.timeout_seconds,
                       min_free_gb=args.min_free_gb)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
