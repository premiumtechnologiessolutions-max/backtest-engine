#!/usr/bin/env python3
"""Execute frozen QS01 once on 2012–2016 design data only.

No period/threshold arguments are exposed. Never loads 2017+ or searches
parameters. Raw quotes and detailed research ledgers stay outside Git.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from norisk_quant.data import fingerprint_loaded_m1, quality, read_source, sha256_file
from norisk_quant.fast_engine import run_fast
from norisk_quant.quote_stress import quote_stress_signals, qs01_settings
from norisk_quant.report import report

YEARS = (2012, 2013, 2014, 2015, 2016)
FROZEN_SOURCE_ZIP_SHA256 = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"


def _code_fingerprints(root: Path) -> dict:
    paths = [
        "src/norisk_quant/quote_stress.py", "src/norisk_quant/model.py",
        "src/norisk_quant/execution.py", "src/norisk_quant/fast_engine.py",
        "src/norisk_quant/accounting.py", "src/norisk_quant/data.py",
        "src/norisk_quant/report.py", "src/norisk_quant/gaps.py",
        "scripts/research_qs01_design.py",
        "docs/PRE_REGISTERED_QS01_QUOTE_STRESS_2026-10-25.md",
    ]
    return {path: sha256_file(root / path) for path in paths}


def _git_checkpoint(root: Path) -> dict:
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
        return {"head_before_run": head, "working_tree_dirty": bool(dirty)}
    except (OSError, subprocess.CalledProcessError):
        return {"head_before_run": None, "working_tree_dirty": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    # This command must never scatter raw quotes or private trade files into
    # a tracked source directory by an accidental --out choice.
    if out == root or root in out.parents:
        parser.error("--out must be outside the source repository")
    out.mkdir(parents=True, exist_ok=True)
    code_before = _code_fingerprints(root)
    parts, source_rows = [], []
    for year in YEARS:
        path = args.source_dir / f"{year}.json"
        part = read_source(path)
        if (part.index.year != year).any():
            raise ValueError(f"Annual file {year} includes another year")
        loaded_hash = fingerprint_loaded_m1(part)  # finite all original quotes, exact minute opens
        source_rows.append({
            "year": year, "file_sha256": sha256_file(path),
            "loaded_m1_sha256": loaded_hash, "quality": quality(part),
        })
        parts.append(part)
        print(json.dumps({"stage": "source_loaded", "year": year, "m1_rows": len(part)}), flush=True)
    minutes = pd.concat(parts).sort_index()
    del parts
    if minutes.index.has_duplicates or minutes.index.min().year != 2012 or minutes.index.max().year != 2016:
        raise ValueError("Invalid continuous design range")
    signals = quote_stress_signals(minutes)
    print(json.dumps({"stage": "frozen_signals", "count": len(signals)}), flush=True)
    settings = qs01_settings()
    result = run_fast(minutes, signals, settings)
    if _code_fingerprints(root) != code_before:
        raise RuntimeError("Code changed during design run; evidence is not reproducible")
    provenance = {
        "original_zip_sha256_in_preregistration": FROZEN_SOURCE_ZIP_SHA256,
        "original_zip_identity_verified": False,
        "identity_limitation": "Original ZIP unavailable. Per-file and normalized quote hashes identify this local extracted dataset; they do not authenticate identity to the frozen ZIP.",
        "annual_sources": source_rows,
        "continuous_design_loaded_m1_sha256": fingerprint_loaded_m1(minutes),
        "code_sha256": code_before,
        **_git_checkpoint(root),
        "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
    }
    summary = report(
        result, settings, out, source="private local extracted annual JSON, 2012–2016 only",
        provenance=provenance,
        run_parameters={
            "hypothesis": "QS01", "stage": "frozen_design_only",
            "years": list(YEARS), "no_parameter_search": True,
            "atr_seed": "SMA20 of contiguous true ranges with prior close; Wilder recursion alpha1/20, reset at gaps",
            "time_exit_priority": "observed open stop/target, then scheduled time exit, before current M1 high/low",
        },
    )
    trades = result.trades
    realized = result.equity["realized_pnl"]
    realized_dd = realized.cummax().clip(lower=0) - realized
    monthly = pd.read_csv(out / "monthly.csv")
    duration = (
        pd.to_datetime(trades["closed_at"], utc=True) - pd.to_datetime(trades["entry_at"], utc=True)
    ).dt.total_seconds() / 60 if len(trades) else pd.Series(dtype=float)
    checks = {
        "at_least_200_trades": len(trades) >= 200,
        "net_positive": summary["net_pnl"] > 0,
        "profit_factor_above_1_10": summary["profit_factor"] is not None and summary["profit_factor"] > 1.10,
        "at_least_31_of_60_positive_realized_months": summary["months_observed"] == 60 and summary["positive_months"] >= 31,
    }
    outcome = {
        "hypothesis": "QS01", "evaluation": "DESIGN_2012_2016_ONLY",
        "status": "DESIGN_GATE_PASSED" if all(checks.values()) else "REJECTED_ON_DESIGN",
        "later_periods_loaded": False, "parameters_tuned": False,
        "design_gate": checks, "signal_count": len(signals),
        "expired_signals": result.expired_signals, "pending_at_end": result.pending_at_end,
        "m1_rows": len(minutes), "source_fingerprints": provenance,
        "trades": len(trades), "net_pnl": summary["net_pnl"],
        "total_fees": summary["total_fees"], "profit_factor": summary["profit_factor"],
        "positive_months": summary["positive_months"], "months": summary["months_observed"],
        "worst_month": float(monthly["net_pnl"].min()),
        "observed_floating_equity_drawdown": summary["max_drawdown_observed_m1"],
        "realized_equity_drawdown": float(realized_dd.max()),
        "month_end_equity_drawdown": summary["max_drawdown_month_end"],
        "exit_reason_counts": trades["exit_reason"].value_counts().to_dict(),
        "ambiguous_m1_stop_first_count": int((trades["exit_reason"] == "ambiguous_stop_first").sum()),
        "gap_through_stop_count": int((trades["exit_reason"] == "gap_stop").sum()),
        "trades_with_missing_minute_exposure": int((trades["gap_minutes"] > 0).sum()),
        "total_trade_missing_minutes": int(trades["gap_minutes"].sum()),
        "total_elapsed_position_minutes": float(duration.sum()),
        "max_elapsed_position_minutes": float(duration.max()) if len(duration) else 0,
        "accounting_checks": summary["accounting_checks"],
        "evidence_limit": "Synthetic same-BID M1 execution and observed marks; no actual tick paths, broker-fill or future-profit evidence. Design data only; no validation/OOS claim.",
    }
    (out / "design_outcome.json").write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    print(json.dumps({key: outcome[key] for key in (
        "status", "m1_rows", "signal_count", "trades", "net_pnl", "total_fees", "profit_factor",
        "positive_months", "months", "worst_month", "accounting_checks", "design_gate",
    )}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
