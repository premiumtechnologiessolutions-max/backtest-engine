"""Offline read-only No Risk FX quant research terminal.

Renders audited factory-registry METADATA, never a trading signal. No network,
no private XAUUSD quotes, and no inference that a test is clean OOS.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import quote

try:
    from scripts.audit_strategy_factory_registry import audit_registry
except ModuleNotFoundError:  # direct script invocation from repository root
    from audit_strategy_factory_registry import audit_registry

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "research" / "strategy_factory_registry.json"
SAFE_REPORT = re.compile(r"^(?:docs|research)/[A-Za-z0-9._/-]+$")


def _nonnegative_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name}: expected nonnegative integer")
    return value


def dashboard_model(registry: dict) -> dict:
    """Reconcile totals before accepting any registry values into the UI."""
    totals = audit_registry(registry)
    rows = []
    for batch in registry["completed_batches"]:
        ident = batch["id"]
        report = batch.get("report")
        if report is not None and (
            type(report) is not str or not SAFE_REPORT.fullmatch(report)
            or ".." in Path(report).parts
        ):
            raise ValueError(f"Unsafe report path: {ident}")
        active = batch.get("active_annual_replays",
                           batch.get("annual_replays_with_filled_trades"))
        if active is None:
            active = 0 if ident == "NRF-FAC-005" else batch.get("completed_annual_replays")
        rows.append({
            "id": str(ident),
            "family": str(batch.get("family", "Not recorded")),
            "status": str(batch.get("status", "UNVERIFIED")),
            "specs": _nonnegative_integer(batch["unique_parameter_specs"], f"{ident} specs"),
            "active_replays": _nonnegative_integer(active, f"{ident} active"),
            "best_positive_months": _nonnegative_integer(
                batch["maximum_positive_months_out_of_24"], f"{ident} months"),
            "passing_24_of_24": _nonnegative_integer(
                batch["configs_24_of_24"], f"{ident} full-month passes"),
            "report": report,
        })
    if sum(row["passing_24_of_24"] for row in rows) != totals["strictly_positive_every_month_in_both_years"]:
        raise ValueError("Monthly pass count is inconsistent")
    return {
        "updated_utc": str(registry.get("updated_utc", "unknown")),
        "research_status": str(registry.get("research_status", "UNVERIFIED")),
        "specifications": totals["distinct_parameter_specs"],
        "annual_replays": totals["yearly_backtests"],
        "families": totals["independent_hypothesis_families"],
        "monthly_observations": totals["exit_booked_monthly_points"],
        "passing_24_of_24": totals["strictly_positive_every_month_in_both_years"],
        "fee": registry["fixed_roundtrip_all_in_fee_usd_per_oz"],
        "rows": rows,
    }


def render_html(model: dict) -> str:
    """Render audited registry metadata through the responsive Quant Terminal."""
    try:
        from scripts.research_terminal_ui import render_premium_html
    except ModuleNotFoundError:  # direct script invocation
        from research_terminal_ui import render_premium_html
    return render_premium_html(model)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "reports" / "research_terminal.html")
    parser.add_argument("--evidence-commit", type=str,
                        help="Optional exact 40-character commit SHA for immutable report links; target existence is not verified")
    parser.add_argument("--include-local-jobs", action="store_true",
                        help="Opt in to verified local queue metadata in offline HTML")
    parser.add_argument("--include-local-month-plans", action="store_true",
                        help="Opt in to verified immutable local month-plan snapshots (requires --include-local-jobs)")
    parser.add_argument("--verified-monthly-plan", type=Path,
                        help="Opt in to fresh private canonical batch re-audit")
    parser.add_argument("--verified-monthly-output", type=Path,
                        help="Local canonical batch output to re-audit")
    parser.add_argument("--verified-monthly-equity-pins", type=Path,
                        help="Optional independently frozen M1 equity SHA256 pins")
    args = parser.parse_args(argv)
    if bool(args.verified_monthly_plan) != bool(args.verified_monthly_output):
        parser.error("--verified-monthly-plan and --verified-monthly-output are required together")
    if args.verified_monthly_equity_pins and not args.verified_monthly_plan:
        parser.error("--verified-monthly-equity-pins requires --verified-monthly-plan")
    if args.include_local_month_plans and not args.include_local_jobs:
        parser.error("--include-local-month-plans requires --include-local-jobs")
    if args.evidence_commit is not None and not re.fullmatch(r"[0-9a-f]{40}", args.evidence_commit):
        parser.error("--evidence-commit must be an exact lowercase 40-character Git commit SHA")
    model = dashboard_model(json.loads(args.registry.read_text(encoding="utf-8")))
    if args.evidence_commit is not None:
        model["evidence_commit"] = args.evidence_commit
    if args.verified_monthly_plan:
        try:
            from scripts import research_batch_monthly_scorecard as scorecard
            from scripts import research_batch_orchestrator as lab
        except ModuleNotFoundError as exc:
            if exc.name != "scripts":
                raise
            import research_batch_monthly_scorecard as scorecard
            import research_batch_orchestrator as lab
        plan = lab.read_strict_json(args.verified_monthly_plan)
        pins = (lab.read_strict_json(args.verified_monthly_equity_pins)
                if args.verified_monthly_equity_pins else None)
        # Re-read and reconcile canonical source on the exact checkout.
        # A precomputed scorecard JSON is never accepted as evidence.
        model["verified_monthly"] = scorecard.scorecard(
            plan, args.verified_monthly_output, equity_pins=pins)
    if args.include_local_jobs:
        try:
            from scripts.research_job_queue import list_jobs
        except ModuleNotFoundError:  # direct invocation from repository root
            from research_job_queue import list_jobs
        # Invalid, tampered or unsafe local queue records fail closed.
        model["jobs"] = list_jobs(ROOT)
    if args.include_local_month_plans:
        if len(model["jobs"]) > 20:
            raise ValueError("Monthly plan export is capped at 20 local jobs")
        try:
            from scripts.research_job_plan_snapshot import verify_plan
        except ModuleNotFoundError:  # direct invocation from repository root
            from research_job_plan_snapshot import verify_plan
        # Every snapshot is rechecked against exact clean-checkout preflight.
        # Missing, stale, tampered, or unsafe snapshots abort the entire export.
        model["monthly_plans"] = [verify_plan(ROOT, job["fingerprint"])
                                  for job in model["jobs"]]
    try:
        from scripts.research_terminal_export import write_private_html
    except ModuleNotFoundError:  # direct script invocation
        from research_terminal_export import write_private_html
    write_private_html(args.out, render_html(model))
    print(json.dumps({
        "status": "AUDITED_METADATA_ONLY_NOT_OOS_CERTIFIED",
        "html": str(args.out),
        "families": len(model["rows"]),
        "specifications": model["specifications"],
        "passing_24_of_24": model["passing_24_of_24"],
        "local_jobs_included": args.include_local_jobs,
        "verified_monthly_included": args.verified_monthly_plan is not None,
        "local_jobs": len(model["jobs"]) if args.include_local_jobs else None,
        "local_month_plans": len(model["monthly_plans"]) if args.include_local_month_plans else None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
