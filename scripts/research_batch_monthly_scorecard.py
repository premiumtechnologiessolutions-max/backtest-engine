"""Offline, read-only monthly risk audit of already completed frozen batches."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
try:
    from scripts import research_batch_orchestrator as lab
except ModuleNotFoundError:
    import research_batch_orchestrator as lab

def scorecard(plan: dict, output: Path) -> dict:
    jobs, digest = lab.expand(plan)
    if len(jobs) > 500:
        raise ValueError("Scorecard maximum is 500 jobs")
    source = Path(plan["dataset"])
    if source.is_symlink() or not source.is_file():
        raise ValueError("Private source archive missing or unsafe")
    if lab.file_sha(source) != plan["source_sha256"]:
        raise ValueError("Private source SHA256 mismatch")
    if lab.checkout_commit() != plan["engine_commit"]:
        raise ValueError("Frozen Git revision mismatch")
    output = Path(output)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("Unsafe batch output directory")
    manifest = lab.read_strict_json(output / "batch_manifest.json")
    if (not isinstance(manifest, dict)
        or set(manifest) != {"schema", "plan_sha256", "source_sha256", "engine_commit", "results"}
        or manifest["schema"] != lab.SCHEMA
        or manifest["plan_sha256"] != digest
        or manifest["source_sha256"] != plan["source_sha256"]
        or manifest["engine_commit"] != plan["engine_commit"]
        or not isinstance(manifest["results"], dict)):
        raise ValueError("Frozen batch manifest mismatch")
    if not set(manifest["results"]).issubset({j["id"] for j in jobs}):
        raise ValueError("Unknown job in batch manifest")
    results = []
    for job in jobs:
        name = job["id"]
        stored = manifest["results"].get(name)
        if stored is None:
            continue
        if not isinstance(stored, dict) or stored.get("status") != lab.PASSED:
            raise ValueError("Failed or ambiguous result: " + name)
        folder = output / "runs" / name
        if folder.is_symlink():
            raise ValueError("Unsafe run directory")
        verified = lab.audit_run(folder, job["spec"], plan["source_sha256"], plan["engine_commit"])
        if verified != stored:
            raise ValueError("Stored result differs from canonical audit")
        rows = lab.read_ledger_csv(folder / "monthly.csv")
        if lab.file_sha(folder / "monthly.csv") != verified["monthly_sha256"]:
            raise ValueError("Monthly evidence changed during scorecard audit")
        pnl = verified["monthly_net_pnl"]
        if [r.get("period") for r in rows] != list(pnl):
            raise ValueError("Monthly row ordering mismatch")
        months = [{
            "month_utc": r["period"],
            "net_usd_per_oz": lab.finite(pnl[r["period"]]),
            "trades": lab.count(r.get("trades")),
            "all_in_fees_usd_per_oz": lab.finite(r.get("total_cost"), nonnegative=True),
            "observed_m1_samples": lab.count(r.get("observed_m1_samples")),
        } for r in rows]
        if not months:
            raise ValueError("Missing monthly evidence")
        worst = min(months, key=lambda m: (m["net_usd_per_oz"], m["month_utc"]))
        results.append({
            "id": name, "status": "HISTORICAL_EXPOSED_STANDALONE_NOT_APPROVED",
            "trades": verified["trades"],
            "positive_months": sum(m["net_usd_per_oz"] > 0 for m in months),
            "months_observed": len(months),
            "zero_trade_months": sum(m["trades"] == 0 for m in months),
            "worst_month_utc": worst["month_utc"],
            "worst_month_net_usd_per_oz": worst["net_usd_per_oz"],
            "net_usd_per_oz": verified["net_pnl"],
            "all_in_fees_usd_per_oz": verified["total_cost"],
            "observed_m1_floating_drawdown_usd_per_oz": None,
            "shared_capacity_verified": False, "clean_prospective_oos": False,
            "monthly": months,
            "evidence_sha256": {k: verified[k] for k in (
                "summary_sha256", "monthly_sha256", "weekly_sha256", "trades_sha256")},
        })
    return {
        "status": "RE_AUDITED_HISTORICAL_STANDALONE_NOT_OOS_NOT_APPROVED",
        "source_sha256_verified_locally": True,
        "plan_sha256": digest,
        "defined_parameter_jobs": len(jobs),
        "reconciled_executed_jobs": len(results),
        "not_executed_jobs": len(jobs) - len(results),
        "independent_hypotheses": None,
        "shared_capacity_portfolio_net_usd_per_oz": None,
        "floating_m1_drawdown_status": "N/A_NOT_IN_VERIFIED_MONTHLY_LEDGER",
        "prospective_months": 0, "approved_strategies": 0,
        "jobs": results,
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(scorecard(lab.read_strict_json(args.plan), args.out), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
