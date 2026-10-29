"""Offline, read-only monthly risk audit of already completed frozen batches."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
try:
    from scripts import research_batch_orchestrator as lab
except ModuleNotFoundError:
    import research_batch_orchestrator as lab

try:
    from scripts import research_equity_m1_audit as equity_audit
except ModuleNotFoundError:
    import research_equity_m1_audit as equity_audit


def validate_equity_pins(pins: dict | None, plan: dict, digest: str,
                         manifest: dict) -> dict:
    """Require independently frozen, plan-scoped M1 hashes; never self-pin."""
    if pins is None:
        return {}
    if (type(pins) is not dict
            or set(pins) != {"schema", "plan_sha256", "source_sha256",
                             "engine_commit", "jobs"}
            or pins["schema"] != "NRFX_EQUITY_PINS_V1"
            or pins["plan_sha256"] != digest
            or pins["source_sha256"] != plan["source_sha256"]
            or pins["engine_commit"] != plan["engine_commit"]
            or type(pins["jobs"]) is not dict):
        raise ValueError("Invalid or stale independently frozen equity pin manifest")
    accepted = manifest["results"]
    for ident, hashes in pins["jobs"].items():
        if (type(ident) is not str or ident not in accepted
                or not isinstance(accepted[ident], dict)
                or accepted[ident].get("status") != lab.PASSED):
            raise ValueError("Equity pin references unexecuted or failed job")
        if (type(hashes) is not dict
                or set(hashes) != {"summary.json", "monthly.csv", "equity_m1.csv"}
                or any(type(value) is not str or not lab.HEX64.fullmatch(value)
                       for value in hashes.values())):
            raise ValueError("Invalid independently frozen equity evidence hashes")
        if (hashes["summary.json"] != accepted[ident]["summary_sha256"]
                or hashes["monthly.csv"] != accepted[ident]["monthly_sha256"]):
            raise ValueError("Equity pins conflict with original canonical manifest")
    return pins["jobs"]


def monthly_downside(months: list[dict], start: str, end: str) -> dict:
    """Risk from source-reconciled exit-booked months, not M1 floating equity.

    A three-month window is reported ONLY when all three full UTC calendar
    months are present and the frozen request covers every calendar day.
    Partial edge months remain visible, never silently treated as full months.
    """
    from calendar import monthrange
    from datetime import date
    import re

    if type(months) is not list or not months:
        raise ValueError("Missing observed months for downside metrics")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError("Reversed monthly risk window")
    first_index = first.year * 12 + first.month - 1
    last_index = last.year * 12 + last.month - 1
    if last_index - first_index > 360:
        raise ValueError("Monthly audit window exceeds 361 calendar months")
    ordered = []
    partial = []
    previous = None
    longest = run = nonpositive = 0
    worst = None
    worst_window = None
    for item in months:
        if type(item) is not dict:
            raise ValueError("Invalid observed monthly risk row")
        label = item.get("month_utc")
        if type(label) is not str or not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", label):
            raise ValueError("Invalid observed UTC month")
        year, month = map(int, label.split("-"))
        beginning = date(year, month, 1)
        ending = date(year, month, monthrange(year, month)[1])
        index = year * 12 + month - 1
        if (previous is not None and index <= previous) or ending < first or beginning > last:
            raise ValueError("Unordered or out-of-window UTC month")
        net = lab.finite(item.get("net_usd_per_oz"))
        trades = lab.count(item.get("trades"))
        complete = first <= beginning and ending <= last
        if not complete:
            partial.append(label)
        if previous is not None and index != previous + 1:
            run = 0
        if net <= 0:
            run += 1
            nonpositive += 1
        else:
            run = 0
        longest = max(longest, run)
        ordered.append((index, label, net, complete, trades))
        if len(ordered) >= 3:
            a, c, d = ordered[-3:]
            if (a[3] and c[3] and d[3]
                    and c[0] == a[0] + 1 and d[0] == c[0] + 1):
                total = round(a[2] + c[2] + d[2], 8)
                if worst is None or total < worst:
                    worst = total
                    worst_window = [a[1], d[1]]
        previous = index
    observed_months = {row[1] for row in ordered}
    missing_months = [
        f"{index // 12:04d}-{index % 12 + 1:02d}"
        for index in range(first_index, last_index + 1)
        if f"{index // 12:04d}-{index % 12 + 1:02d}" not in observed_months
    ]
    return {
        "missing_requested_calendar_months_utc": missing_months,
        "requested_calendar_month_coverage_complete": not missing_months,
        "nonpositive_months": nonpositive,
        "months_with_trades": sum(item[4] > 0 for item in ordered),
        "longest_nonpositive_observed_month_streak": longest,
        "partial_requested_calendar_months_utc": partial,
        "worst_three_complete_calendar_months_net_usd_per_oz": worst,
        "worst_three_complete_calendar_months_window_utc": worst_window,
    }


def scorecard(plan: dict, output: Path, *, equity_pins: dict | None = None) -> dict:
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
    pinned = validate_equity_pins(equity_pins, plan, digest, manifest)
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
        downside = monthly_downside(months, job["spec"]["start"], job["spec"]["end"])
        if not downside["requested_calendar_month_coverage_complete"]:
            raise ValueError("Canonical monthly ledger missing requested UTC calendar months")
        floating_dd = None
        for month in months:
            month["max_observed_m1_global_peak_drawdown_usd_per_oz"] = None
            month["observed_m1_gap_events_from_prior_mark"] = None
        if name in pinned:
            # Recompute from the actual canonical M1 equity file. Never trust
            # a submitted numeric risk report or derive a hash from that file.
            verified_equity = equity_audit.audit_equity(
                folder, source, plan["source_sha256"], plan["engine_commit"],
                pinned[name])
            equity_months = verified_equity["monthly"]
            if len(equity_months) != len(months):
                raise ValueError("Pinned M1 month coverage differs from P/L ledger")
            for month, observed in zip(months, equity_months):
                if (month["month_utc"] != observed["month_utc"]
                        or month["observed_m1_samples"] != observed["observed_m1_samples"]):
                    raise ValueError("Pinned M1 month or sample count mismatch")
                month["max_observed_m1_global_peak_drawdown_usd_per_oz"] = (
                    observed["max_observed_m1_global_peak_drawdown_usd_per_oz"])
                month["observed_m1_gap_events_from_prior_mark"] = (
                    observed["observed_gap_events_from_prior_mark"])
            floating_dd = verified_equity[
                "max_observed_m1_global_peak_drawdown_usd_per_oz"]
        worst = min(months, key=lambda m: (m["net_usd_per_oz"], m["month_utc"]))
        results.append({
            "id": name, "status": "HISTORICAL_EXPOSED_STANDALONE_NOT_APPROVED",
            "trades": verified["trades"],
            "evaluation_start_utc": job["spec"]["start"],
            "evaluation_end_utc": job["spec"]["end"],
            "positive_months": sum(m["net_usd_per_oz"] > 0 for m in months),
            "months_observed": len(months),
            "zero_trade_months": sum(m["trades"] == 0 for m in months),
            **downside,
            "worst_month_utc": worst["month_utc"],
            "worst_month_net_usd_per_oz": worst["net_usd_per_oz"],
            "net_usd_per_oz": verified["net_pnl"],
            "all_in_fees_usd_per_oz": verified["total_cost"],
            "observed_m1_floating_drawdown_usd_per_oz": floating_dd,
            "shared_capacity_verified": False, "clean_prospective_oos": False,
            "monthly": months,
            "evidence_sha256": {
                **{k: verified[k] for k in (
                    "summary_sha256", "monthly_sha256", "weekly_sha256", "trades_sha256")},
                **({"equity_m1_sha256": pinned[name]["equity_m1.csv"]}
                   if name in pinned else {}),
            },
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
        "floating_m1_drawdown_status": (
            "HASH_PINNED_OBSERVED_M1_FOR_ALL_EXECUTED"
            if results and len(pinned) == len(results)
            else "PARTIAL_HASH_PINNED_OBSERVED_M1"
            if pinned else "N/A_NO_INDEPENDENT_EQUITY_HASH_PINS"),
        "hash_pinned_m1_jobs": len(pinned),
        "unverified_floating_m1_jobs": len(results) - len(pinned),
        "prospective_months": 0, "approved_strategies": 0,
        "jobs": results,
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--equity-pins", type=Path,
                        help="Previously independently frozen, plan-scoped M1 evidence hashes")
    args = parser.parse_args(argv)
    pins = lab.read_strict_json(args.equity_pins) if args.equity_pins else None
    print(json.dumps(scorecard(lab.read_strict_json(args.plan), args.out,
                               equity_pins=pins), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
