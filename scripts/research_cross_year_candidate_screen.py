"""Compare the SAME frozen strategy parameter identity across full annual runs.

Requires canonical annual evidence, historical-exposed only, no live or OOS
certification. Training years ONLY determine rank; later review is descriptive.
"""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
from pathlib import Path

from norisk_quant.search_multiplicity import exact_joint_signflip

try:
    from scripts import research_batch_orchestrator as batch
    from scripts import research_candidate_screen as screen
    from scripts.generate_quant_research_grid import parse_years
    from scripts.research_terminal_export import write_private_html
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    import research_batch_orchestrator as batch
    import research_candidate_screen as screen
    from generate_quant_research_grid import parse_years
    from research_terminal_export import write_private_html

SCHEMA = "NRFX_CROSS_YEAR_EXPLORATORY_V1"


def strategy_key(spec: dict) -> str:
    """Ignore annual research window, never ignore execution or parameters."""
    return hashlib.sha256(batch.canonical({
        k: v for k, v in spec.items() if k not in ("start", "end")
    })).hexdigest()


def screen_cross_year(plan: dict, manifest: dict, runs_root: Path, *,
                      train_years: tuple[int, ...], review_years: tuple[int, ...],
                      min_train_trades: int = 20,
                      min_positive_fraction: float = 0.6) -> dict:
    if (not train_years or not review_years
            or train_years != tuple(sorted(set(train_years)))
            or review_years != tuple(sorted(set(review_years)))
            or max(train_years) >= min(review_years)):
        raise ValueError("Training years must strictly precede review years")
    if (any(type(y) is not int or not 2010 <= y <= 2026
            for y in train_years + review_years)):
        raise ValueError("Invalid comparison year")
    if type(min_train_trades) is not int or min_train_trades < 1:
        raise ValueError("Invalid minimum training trades")
    if (type(min_positive_fraction) not in (int, float)
            or not 0 < min_positive_fraction <= 1):
        raise ValueError("Invalid positive-month fraction")
    jobs, plan_sha = batch.expand(plan)
    if (type(manifest) is not dict or set(manifest) != {
            "schema", "plan_sha256", "source_sha256", "engine_commit", "results"}
            or manifest["schema"] != batch.SCHEMA
            or manifest["plan_sha256"] != plan_sha
            or manifest["source_sha256"] != plan["source_sha256"]
            or manifest["engine_commit"] != plan["engine_commit"]
            or type(manifest["results"]) is not dict):
        raise ValueError("Frozen annual batch manifest mismatch")
    defined = {}
    groups = {}
    for job in jobs:
        ident, spec = job["id"], job["spec"]
        year = int(spec["start"][:4])
        if (spec["start"] != f"{year}-01-01"
                or spec["end"] != f"{year}-12-31"):
            raise ValueError("Cross-year screen requires exact full UTC calendar years")
        key = strategy_key(spec)
        if year in groups.setdefault(key, {}):
            raise ValueError("Repeated annual experiment for the same strategy")
        groups[key][year] = job
        defined[ident] = spec
    if not set(manifest["results"]).issubset(defined):
        raise ValueError("Unrecognized annual experiment in manifest")
    verified = {}
    for ident, saved in manifest["results"].items():
        if type(saved) is not dict or saved.get("status") != batch.PASSED:
            raise ValueError("Unverified annual run blocks cross-year screening")
        folder = runs_root / ident
        if folder.is_symlink():
            raise ValueError("Unsafe annual result path")
        audited = batch.audit_run(folder, defined[ident],
                                  plan["source_sha256"], plan["engine_commit"])
        if saved != audited:
            raise ValueError("Annual evidence changed since reconciliation")
        monthly_rows = batch.read_ledger_csv(folder / "monthly.csv")
        if batch.file_sha(folder / "monthly.csv") != audited["monthly_sha256"]:
            raise ValueError("Annual monthly ledger changed during screening")
        verified[ident] = (audited, {r["period"]: batch.count(r["trades"])
                                     for r in monthly_rows})
    relevant = train_years + review_years
    compared, incomplete = [], []
    for key, annual in sorted(groups.items()):
        unavailable = [y for y in relevant
                       if y not in annual or annual[y]["id"] not in verified]
        if unavailable:
            incomplete.append({"candidate_id": key, "missing_years": unavailable})
            continue
        all_pnl, all_trades = {}, {}
        annual_training_net = []
        gap_training = forced_training = gap_review = forced_review = 0
        for y in relevant:
            job = annual[y]
            record, counts = verified[job["id"]]
            expected_months = [f"{y}-{month:02d}" for month in range(1, 13)]
            if set(record["monthly_net_pnl"]) != set(expected_months) or set(counts) != set(expected_months):
                raise ValueError("Annual ledger lacks complete 12-month coverage")
            all_pnl.update(record["monthly_net_pnl"])
            all_trades.update(counts)
            if y in train_years:
                annual_training_net.append(round(sum(record["monthly_net_pnl"].values()), 8))
                gap_training += record["uncertain_gap_trade_month_assignments"]
                forced_training += record["synthetic_end_of_data_closures"]
            else:
                gap_review += record["uncertain_gap_trade_month_assignments"]
                forced_review += record["synthetic_end_of_data_closures"]
        training_months = [f"{y}-{m:02d}" for y in train_years for m in range(1, 13)]
        review_months = [f"{y}-{m:02d}" for y in review_years for m in range(1, 13)]
        train = screen.metrics(training_months, all_pnl, all_trades)
        later = screen.metrics(review_months, all_pnl, all_trades)
        passed = (
            train["trades"] >= min_train_trades
            and train["positive_months"] / train["months"] >= min_positive_fraction
            and train["net_pnl_usd_per_oz"] > 0
            and gap_training == 0 and forced_training == 0
        )
        sample = annual[train_years[0]]["spec"]
        compared.append({
            "candidate_id": key, "job_id": key, "identity": {
                k: v for k, v in sample.items() if k not in ("start", "end")},
            "training_screen": "PASSED_EXPLORATORY" if passed else "REJECTED_EXPLORATORY",
            "train": train, "later_review_descriptive_only": later,
            "training_annual_net_usd_per_oz": annual_training_net,
            "training_uncertain_gap_trades": gap_training,
            "training_synthetic_forced_closes": forced_training,
            "review_uncertain_gap_trades": gap_review,
            "review_synthetic_forced_closes": forced_review,
            "annual_job_ids": {str(y): annual[y]["id"] for y in relevant},
        })
    # Compute only over the COMPLETE defined candidate family. A partially
    # completed factory can hide unexecuted competing strategies.
    multiplicity = {"status": "NOT_COMPUTED_UNIVERSE_INCOMPLETE_OR_EMPTY"}
    if not incomplete and compared:
        diagnostic = exact_joint_signflip({
            entry["candidate_id"]: entry["training_annual_net_usd_per_oz"]
            for entry in compared
        })
        multiplicity = {k: v for k, v in diagnostic.items() if k != "results"}
        for entry in compared:
            entry["training_signflip_diagnostic_only"] = diagnostic["results"][entry["candidate_id"]]
    # Partially executed candidate universes are NOT comparable: unseen
    # alternatives could outperform all observed candidates. Fail closed.
    if incomplete:
        compared.sort(key=lambda item: item["candidate_id"])
        for item in compared:
            item["training_rank"] = None
            item["training_screen"] = "NOT_ELIGIBLE_BATCH_INCOMPLETE"
    else:
        compared.sort(key=screen.training_rank_key)
        for rank, item in enumerate(compared, 1):
            item["training_rank"] = rank
    return {
        "schema": SCHEMA,
        "research_status": ("HISTORICAL_EXPOSED_SCREEN_COMPLETE" if not incomplete
                            else "INCOMPLETE_ANNUAL_COVERAGE"),
        "independent_oos_proven": False,
        "selection_policy": "TRAIN_ONLY_HEURISTIC_MAXT_DIAGNOSTIC_NOT_VALIDATION",
        "multiplicity_diagnostic": multiplicity,
        "plan_sha256": plan_sha,
        "source_sha256": plan["source_sha256"],
        "engine_commit": plan["engine_commit"],
        "train_years": list(train_years), "review_years": list(review_years),
        "defined_annual_jobs": len(jobs), "audited_annual_jobs": len(verified),
        "candidate_identifiers": len(groups), "compared_candidates": len(compared),
        "incomplete_candidates": incomplete, "results": compared,
    }


def render_html(report: dict) -> str:
    heads = ["Rank", "Strategy", "TF", "Train +months", "Train net/oz",
             "Train DD/oz", "Review net/oz", "Screen"]
    rows = []
    for item in report["results"]:
        a, b = item["train"], item["later_review_descriptive_only"]
        identity = item["identity"]
        values = [str(item["training_rank"]) if item["training_rank"] is not None else "—", identity["strategy"],
                  identity["timeframe"], str(a["positive_months"]),
                  f'{a["net_pnl_usd_per_oz"]:+.2f}',
                  f'{a["max_month_end_drawdown_usd_per_oz"]:.2f}',
                  f'{b["net_pnl_usd_per_oz"]:+.2f}', item["training_screen"]]
        rows.append("<tr>"+"".join("<td>"+escape(v)+"</td>" for v in values)+"</tr>")
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>No Risk FX | Cross-year research</title>'
            '<style>:root{color-scheme:dark;background:#071526;color:#e9efff;font-family:system-ui}'
            'body{padding:24px}h1{color:#d7b36b}.scroll{overflow:auto}'
            'table{border-collapse:collapse;width:100%;white-space:nowrap}'
            'th,td{padding:10px;border-bottom:1px solid #344962;text-align:right}</style>'
            '</head><body><h1>NO RISK FX | Audited cross-year candidate screen</h1>'
            '<p>HISTORICAL EXPOSED ONLY. Not independent OOS or live ready. '
            'Training years alone determine ranking; later review is descriptive. '
            'No multiple-testing correction; drawdown is month-end closed P/L only.</p>'
            f'<p>Defined annual jobs: {report["defined_annual_jobs"]}; '
            f'audited: {report["audited_annual_jobs"]}; '
            f'compared candidates: {report["compared_candidates"]}; '
            f'incomplete: {len(report["incomplete_candidates"])}.</p>'
            '<div class="scroll"><table><thead><tr>'
            + ''.join('<th>'+escape(h)+'</th>' for h in heads)
            + '</tr></thead><tbody>' + ''.join(rows)
            + '</tbody></table></div></body></html>')


def run_file(plan_file: Path, output_dir: Path, *, train_years: tuple[int, ...],
             review_years: tuple[int, ...]) -> dict:
    plan = batch.read_strict_json(plan_file)
    if type(plan) is not dict:
        raise ValueError("Invalid plan")
    data = Path(plan["dataset"])
    if data.is_symlink() or not data.is_file() or batch.file_sha(data) != plan["source_sha256"]:
        raise ValueError("Authorized private source checksum mismatch")
    if batch.checkout_commit() != plan["engine_commit"]:
        raise ValueError("Current code is not frozen engine revision")
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ValueError("Unsafe output path")
    with batch.exclusive_batch_lock(output_dir):
        manifest = batch.read_strict_json(output_dir / "batch_manifest.json")
        report = screen_cross_year(plan, manifest, output_dir / "runs",
                                   train_years=train_years, review_years=review_years)
        batch.atomic_manifest(output_dir / "cross_year_screen.json", report)
        write_private_html(output_dir / "cross_year_screen.html", render_html(report))
        return {k: v for k, v in report.items()
                if k in ("research_status", "defined_annual_jobs", "audited_annual_jobs",
                         "compared_candidates", "independent_oos_proven")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--batch-output", required=True, type=Path)
    parser.add_argument("--train-years", default="2012,2013,2014,2015,2016")
    parser.add_argument("--review-years", default="2017,2018,2019,2020")
    args = parser.parse_args(argv)
    out = run_file(args.plan, args.batch_output,
                   train_years=parse_years(args.train_years),
                   review_years=parse_years(args.review_years))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
