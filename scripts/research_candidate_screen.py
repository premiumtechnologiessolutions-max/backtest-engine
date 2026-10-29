"""Exploratory candidate ranking from audited historical-exposed batch evidence.

Training window alone determines selection and rank. A later review window
cannot influence either. Neither window is certified independent OOS.
"""
from __future__ import annotations

import argparse
from datetime import date
from html import escape
import hashlib
import json
import math
from pathlib import Path
import re

try:
    from scripts import research_batch_orchestrator as batch
    from scripts.research_terminal_export import write_private_html
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    import research_batch_orchestrator as batch
    from research_terminal_export import write_private_html

SCHEMA = "NRFX_EXPLORATORY_CANDIDATE_SCREEN_V1"
MONTH = re.compile(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])\Z")


def months_between(start: str, end: str) -> list[str]:
    if (type(start) is not str or type(end) is not str
            or not MONTH.fullmatch(start) or not MONTH.fullmatch(end)
            or start > end):
        raise ValueError("Invalid YYYY-MM research window")
    first, last = (date.fromisoformat(x + "-01") for x in (start, end))
    result = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return result


def drawdown(values: list[float]) -> float:
    equity = peak = worst = 0.0
    for pnl in values:
        if type(pnl) not in (float, int) or not math.isfinite(pnl):
            raise ValueError("Nonfinite monthly P/L")
        equity += pnl
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return round(worst, 8)


def metrics(months: list[str], pnl: dict, trades: dict) -> dict:
    if not months or any(m not in pnl or m not in trades for m in months):
        raise ValueError("Missing comparison month")
    values = [pnl[m] for m in months]
    counts = [trades[m] for m in months]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("Invalid monthly P/L")
    if any(type(v) is not int or v < 0 for v in counts):
        raise ValueError("Invalid monthly trade count")
    positives = sum(x > 0 for x in values)
    return {
        "months": len(months), "trades": sum(counts),
        "positive_months": positives,
        "positive_month_fraction": round(positives / len(months), 8),
        "net_pnl_usd_per_oz": round(sum(values), 8),
        "worst_month_usd_per_oz": round(min(values), 8),
        "max_month_end_drawdown_usd_per_oz": drawdown(values),
    }


def training_rank_key(row: dict) -> tuple:
    """Review-period data is deliberately excluded from sorting."""
    t = row["train"]
    return (0 if row["training_screen"] == "PASSED_EXPLORATORY" else 1,
            -t["positive_month_fraction"], -t["net_pnl_usd_per_oz"],
            t["max_month_end_drawdown_usd_per_oz"], row["job_id"])


def select(plan: dict, manifest: dict, runs_root: Path, *, train_start: str,
           train_end: str, review_start: str, review_end: str,
           min_train_trades: int = 20,
           min_positive_fraction: float = 0.6) -> dict:
    training = months_between(train_start, train_end)
    review = months_between(review_start, review_end)
    if training[-1] >= review[0]:
        raise ValueError("Review overlaps or precedes training")
    if len(training) < 3 or len(review) < 3:
        raise ValueError("At least three months required per window")
    if type(min_train_trades) is not int or min_train_trades < 1:
        raise ValueError("Invalid minimum training trades")
    if (type(min_positive_fraction) not in (float, int)
            or not math.isfinite(min_positive_fraction)
            or not 0 < min_positive_fraction <= 1):
        raise ValueError("Invalid positive-month fraction")
    jobs, plan_sha = batch.expand(plan)
    if (not isinstance(manifest, dict)
            or set(manifest) != {"schema", "plan_sha256", "source_sha256",
                                "engine_commit", "results"}
            or manifest["schema"] != batch.SCHEMA
            or manifest["plan_sha256"] != plan_sha
            or manifest["source_sha256"] != plan["source_sha256"]
            or manifest["engine_commit"] != plan["engine_commit"]
            or type(manifest["results"]) is not dict):
        raise ValueError("Frozen batch manifest mismatch")
    defined = {j["id"]: j["spec"] for j in jobs}
    if not set(manifest["results"]).issubset(defined):
        raise ValueError("Unknown batch job")
    rows, noncomparable = [], []
    for ident, record in sorted(manifest["results"].items()):
        if type(record) is not dict or record.get("status") != batch.PASSED:
            raise ValueError("Unverified or failed batch run")
        folder = runs_root / ident
        if folder.is_symlink():
            raise ValueError("Unsafe run directory")
        audited = batch.audit_run(folder, defined[ident],
                                  plan["source_sha256"], plan["engine_commit"])
        if audited != record:
            raise ValueError("Manifest and audited evidence disagree")
        monthly = batch.read_ledger_csv(folder / "monthly.csv")
        if batch.file_sha(folder / "monthly.csv") != audited["monthly_sha256"]:
            raise ValueError("Monthly evidence changed during screening")
        trade_counts = {r["period"]: batch.count(r.get("trades")) for r in monthly}
        values = audited["monthly_net_pnl"]
        if not set(training + review).issubset(values) or not set(training + review).issubset(trade_counts):
            noncomparable.append(ident)
            continue
        train = metrics(training, values, trade_counts)
        later = metrics(review, values, trade_counts)
        passed = (train["trades"] >= min_train_trades
                  and (train["positive_months"] / train["months"]) >= min_positive_fraction
                  and train["net_pnl_usd_per_oz"] > 0)
        rows.append({
            "job_id": ident,
            "spec_sha256": hashlib.sha256(batch.canonical(defined[ident])).hexdigest(),
            "strategy": defined[ident]["strategy"],
            "training_screen": "PASSED_EXPLORATORY" if passed else "REJECTED_EXPLORATORY",
            "train": train, "later_review_descriptive_only": later,
        })
    if not rows:
        raise ValueError("No comparable fully audited jobs in both windows")
    rows.sort(key=training_rank_key)
    for rank, row in enumerate(rows, 1):
        row["training_rank"] = rank
    return {
        "schema": SCHEMA,
        "evidence_context": "HISTORICAL_EXPOSED_NOT_OOS_NOT_LIVE_APPROVED",
        "method": "TRAIN_ONLY_RANK_REVIEW_DESCRIPTIVE_NO_MULTIPLE_TESTING_ADJUSTMENT",
        "plan_sha256": plan_sha,
        "engine_commit": plan["engine_commit"],
        "source_sha256": plan["source_sha256"],
        "train_months": training,
        "later_review_months": review,
        "policy": {"min_train_trades": min_train_trades,
                   "min_positive_fraction": float(min_positive_fraction),
                   "require_positive_train_net": True},
        "defined_jobs": len(jobs),
        "audited_jobs": len(manifest["results"]),
        "compared_jobs": len(rows),
        "noncomparable_job_ids": noncomparable,
        "results": rows,
    }


def render(report: dict) -> str:
    cols = ["Rank", "Job", "Strategy", "Train screen", "Train trades",
            "Train +months", "Train net/oz", "Train DD/oz",
            "Review net/oz", "Review +months"]
    rows = []
    for item in report["results"]:
        t, r = item["train"], item["later_review_descriptive_only"]
        values = [str(item["training_rank"]), item["job_id"], item["strategy"],
                  item["training_screen"], str(t["trades"]),
                  f'{t["positive_month_fraction"]:.0%}',
                  f'{t["net_pnl_usd_per_oz"]:+.2f}',
                  f'{t["max_month_end_drawdown_usd_per_oz"]:.2f}',
                  f'{r["net_pnl_usd_per_oz"]:+.2f}',
                  f'{r["positive_month_fraction"]:.0%}']
        rows.append("<tr>" + "".join("<td>" + escape(x) + "</td>" for x in values) + "</tr>")
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>No Risk FX | Historical Candidate Screen</title>'
            '<style>:root{color-scheme:dark;font-family:system-ui;background:#071526;color:#eef3fc}'
            'body{padding:clamp(14px,3vw,42px)}h1{color:#d9b977}'
            'p{max-width:1000px;line-height:1.5;color:#bfcadd}'
            '.wrap{overflow:auto;border:1px solid #3b4e65;border-radius:12px}'
            'table{border-collapse:collapse;white-space:nowrap;width:100%}'
            'td,th{padding:12px;border-bottom:1px solid #2b3b50;text-align:right}'
            'td:nth-child(2),th:nth-child(2){text-align:left}</style></head><body>'
            '<h1>NO RISK FX | Exploratory Candidate Screen</h1>'
            '<p>Historical exposed only: NOT independent OOS, investment advice, or live ready. '
            'Training months exclusively determine ranking and eligibility. '
            'Later review is descriptive, with no multiple-testing correction. '
            'Net P/L includes fixed 0.40 USD/oz fee; monthly drawdown '
            'does not reflect intramonth exposure.</p>'
            '<p>Training: ' + escape(report["train_months"][0]) + '–'
            + escape(report["train_months"][-1]) + ' | Review: '
            + escape(report["later_review_months"][0]) + '–'
            + escape(report["later_review_months"][-1]) + '</p>'
            '<div class="wrap"><table><thead><tr>'
            + ''.join('<th>' + escape(c) + '</th>' for c in cols)
            + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></body></html>')


def build(plan_path: Path, batch_output: Path, *, train_start: str, train_end: str,
          review_start: str, review_end: str, min_train_trades: int = 20,
          min_positive_fraction: float = 0.6) -> dict:
    plan = batch.read_strict_json(plan_path)
    if type(plan) is not dict:
        raise ValueError("Research plan must be an object")
    batch.expand(plan)
    dataset = Path(plan["dataset"]).resolve(strict=True)
    if not dataset.is_file() or batch.file_sha(dataset) != plan["source_sha256"]:
        raise ValueError("Private source archive fingerprint mismatch")
    if batch.checkout_commit() != plan["engine_commit"]:
        raise ValueError("Checkout differs from frozen engine revision")
    if batch_output.is_symlink() or not batch_output.is_dir():
        raise ValueError("Unsafe or missing batch output")
    with batch.exclusive_batch_lock(batch_output):
        manifest = batch.read_strict_json(batch_output / "batch_manifest.json")
        report = select(plan, manifest, batch_output / "runs",
                        train_start=train_start, train_end=train_end,
                        review_start=review_start, review_end=review_end,
                        min_train_trades=min_train_trades,
                        min_positive_fraction=min_positive_fraction)
        batch.atomic_manifest(batch_output / "candidate_screen.json", report)
        write_private_html(batch_output / "candidate_screen.html", render(report))
        return {"compared_jobs": report["compared_jobs"],
                "audited_jobs": report["audited_jobs"],
                "training_passed": sum(r["training_screen"] == "PASSED_EXPLORATORY"
                                       for r in report["results"]),
                "json": str(batch_output / "candidate_screen.json"),
                "html": str(batch_output / "candidate_screen.html"),
                "evidence_context": report["evidence_context"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--batch-output", type=Path, required=True)
    parser.add_argument("--train-start", required=True)
    parser.add_argument("--train-end", required=True)
    parser.add_argument("--review-start", required=True)
    parser.add_argument("--review-end", required=True)
    parser.add_argument("--min-train-trades", type=int, default=20)
    parser.add_argument("--min-positive-fraction", type=float, default=0.6)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.plan, args.batch_output,
                           train_start=args.train_start, train_end=args.train_end,
                           review_start=args.review_start, review_end=args.review_end,
                           min_train_trades=args.min_train_trades,
                           min_positive_fraction=args.min_positive_fraction), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
