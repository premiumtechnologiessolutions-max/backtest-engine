"""Freeze prospective XAUUSD validation BEFORE opening its future data.

This does not execute, read, discover or certify OOS observations. Historical
training is NEVER independent holdout. Only TRAINING-eligible candidates
may be frozen; no-passing-candidate status is an explicit negative result.
"""
from __future__ import annotations

import argparse
from datetime import datetime, date, timezone
from hashlib import sha256
import json
import os
import re
from pathlib import Path
import tempfile

from norisk_quant.research_evolution import _formula
from norisk_quant.research_training_integrity import training_summary
from scripts.materialize_arithmetic_generation import _load_strict
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA

SCHEMA = "NRFX_PROSPECTIVE_VALIDATION_FREEZE_V1"


def freeze_training_selection(input_file: Path, *, start_date: str,
                              end_date: str, output: Path,
                              top_n: int = 3, as_of: date | None = None,
                              embargo_days: int = 30) -> dict:
    if type(top_n) is not int or not 1 <= top_n <= 10:
        raise ValueError("Top N must be a bounded positive integer <=10")
    if type(embargo_days) is not int or not 1 <= embargo_days <= 366:
        raise ValueError("Embargo must be an integer between 1 and 366 days")
    if input_file.is_symlink() or not input_file.is_file():
        raise ValueError("Frozen training input unavailable")
    if (type(start_date) is not str or type(end_date) is not str
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", start_date) is None
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", end_date) is None):
        raise ValueError("Validation dates must be ISO YYYY-MM-DD")
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("Validation dates must be ISO YYYY-MM-DD") from exc
    today = datetime.now(timezone.utc).date() if as_of is None else as_of
    if type(today) is not date or start <= today or (end - start).days < 28:
        raise ValueError("Validation must start after freeze and last >=28 days")
    source, input_sha = _load_strict(input_file)
    proof_path = input_file.with_name(input_file.name + ".evidence.json")
    if proof_path.is_symlink():
        raise ValueError("Symlinked training evidence")
    proof, _ = _load_strict(proof_path)
    years = source.get("years") if type(source) is dict else None
    if (type(years) is not list or not years
            or any(type(y) is not int or not 1900 <= y <= 9998 for y in years)
            or years != sorted(set(years))):
        raise ValueError("Frozen training years must be unique, sorted integers")
    last_training_date = date(years[-1], 12, 31)
    if (start - last_training_date).days < embargo_days:
        raise ValueError("Prospective validation violates training-data embargo")
    if (type(source) is not dict or source.get("schema") !=
            "NRFX_ARITHMETIC_TRAINING_INPUT_V1"
            or type(source.get("years")) is not list
            or type(source.get("candidates")) is not list
            or type(proof) is not dict
            or proof.get("schema") != "NRFX_ARITHMETIC_FEEDBACK_EVIDENCE_V1"
            or proof.get("next_input_sha256") != input_sha
            or proof.get("original_archive_sha256") != SOURCE_SHA
            or proof.get("training_years") != source["years"]
            or proof.get("training_only") is not True
            or proof.get("independent_oos_proven") is not False
            or proof.get("live_trading_authorized") is not False
            or max(source["years"]) >= start.year):
        raise ValueError("Original-source verified training-only evidence required")
    years = tuple(source["years"])
    eligible = []
    seen_identities = set()
    for candidate in source["candidates"]:
        if type(candidate) is not dict or set(candidate) != {"formula", "records"}:
            raise ValueError("Unexpected source candidate fields")
        formula = _formula(candidate["formula"])
        identity = formula.identity()
        if identity in seen_identities:
            raise ValueError("Duplicate candidate identity in prospective freeze")
        seen_identities.add(identity)
        summary = training_summary(candidate["records"], years)
        if summary["screen"] == "PASSED_TRAIN_HEURISTIC_NOT_OOS":
            eligible.append({
                "identity": identity, "formula": candidate["formula"],
                "training_score": summary["training_score"],
                "training_net_usd_per_oz": summary["net_usd_per_oz"],
            })
    eligible.sort(key=lambda x: (-x["training_score"],
                                 -x["training_net_usd_per_oz"], x["identity"]))
    selected = eligible[:top_n]
    freeze_time = datetime.now(timezone.utc).isoformat()
    plan = {
        "schema": SCHEMA,
        "status": ("FROZEN_AWAITING_FUTURE_INDEPENDENT_DATA" if selected
                   else "NO_ELIGIBLE_TRAINING_CANDIDATES_NO_OOS"),
        "freeze_created_utc": freeze_time,
        "prospective_start_utc_date": start_date,
        "prospective_end_utc_date": end_date,
        "train_input_sha256": input_sha,
        "original_training_archive_sha256": SOURCE_SHA,
        "training_years": source["years"],
        "last_training_calendar_date": last_training_date.isoformat(),
        "embargo_days_after_training": embargo_days,
        "training_embargo_verified": True,
        "candidate_count": len(selected),
        "candidates": selected,
        "fixed_all_in_cost_per_ounce": 0.40,
        "rules": {
            "no_refitting_on_prospective_sample": True,
            "full_calendar_month_report_required": True,
            "reference_fast_parity_required": True,
            "source_and_execution_receipts_required": True,
            "broker_tick_validation_separate": True,
            "no_monthly_profit_guarantee": True,
        },
        "prospective_data_accessed": False,
        "independent_oos_proven": False,
        "live_trading_authorized": False,
    }
    # The freeze file must be publish-once: even a typo fix requires a new
    # explicitly versioned plan, never retroactive rewriting after the fact.
    if output.is_symlink() or output.exists() or not output.parent.is_dir():
        raise ValueError("Prospective freeze destination must be unused")
    if any((p / ".git").exists() for p in (output.parent, *output.parent.parents)):
        raise ValueError("Private validation freeze must remain outside Git")
    data = (json.dumps(plan, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    fd, tmp = tempfile.mkstemp(prefix=".nrfx_validation_freeze_", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # No replacement of immutable published registration.
        try:
            os.link(tmp, output)
        except FileExistsError as exc:
            raise ValueError("Prospective freeze was already published") from exc
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {"status": plan["status"], "candidates": len(selected),
            "freeze_sha256": sha256(data).hexdigest(),
            "independent_oos_proven": False}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--training-input", required=True, type=Path)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--top", default=3, type=int)
    ap.add_argument("--embargo-days", default=30, type=int)
    args = ap.parse_args(argv)
    print(json.dumps(freeze_training_selection(
        args.training_input, start_date=args.start, end_date=args.end,
        output=args.out, top_n=args.top,
        embargo_days=args.embargo_days), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
