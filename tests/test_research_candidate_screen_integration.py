"""Six-month synthetic integration: actual canonical audit_run + candidate screen.

No private Gold ZIP or market observations are used; fingerprints are fictitious.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
import json

from scripts import research_batch_orchestrator as batch
from scripts import research_candidate_screen as screen


def write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_six_month_engine_report_is_audited_before_training_screen(tmp_path):
    source, commit, m1 = ("a" * 64, "b" * 40, "c" * 64)
    spec = {"strategy": "ema", "timeframe": "M15", "execution": "fast",
            "start": "2024-01-01", "end": "2024-06-30",
            "parameters": {"fast": 9, "slow": 21, "stop_atr": 1.5, "rr": 2.0}}
    plan = {"schema": batch.SCHEMA, "dataset": str(tmp_path / "private-gold.zip"),
            "source_sha256": source, "engine_commit": commit,
            "exposure_context": "historical_exposed",
            "jobs": [{"id": "candidate-1", **spec}], "grids": []}
    jobs, plan_sha = batch.expand(plan)
    assert len(jobs) == 1
    folder = tmp_path / "runs" / "candidate-1"
    folder.mkdir(parents=True)
    pnl = (4., 3., 2., -2., -2., -2.)
    monthly, weekly, trades = [], [], []
    for month, net in enumerate(pnl, 1):
        day = date(2024, month, 15)
        monday = day - timedelta(days=day.weekday())
        sunday = monday + timedelta(days=6)
        monthly.append({"period": f"2024-{month:02d}", "net_pnl": net,
                        "trades": 1, "total_cost": 0.4,
                        "observed_m1_samples": 100,
                        "uncertain_gap_trades": 0,
                        "synthetic_end_of_data_trades": 0})
        weekly.append({"period": f"{monday.isoformat()}/{sunday.isoformat()}",
                       "net_pnl": net, "trades": 1, "total_cost": 0.4})
        trades.append({"closed_at": f"{day.isoformat()}T12:00:00+00:00",
                       "net_pnl": net, "cost": 0.4})
    write_csv(folder / "monthly.csv", list(monthly[0]), monthly)
    write_csv(folder / "weekly.csv", list(weekly[0]), weekly)
    write_csv(folder / "trades.csv", list(trades[0]), trades)
    summary = {
        "execution": "synthetic_same_reference_bid_ohlc_fixed_all_in_fee",
        "settings": {"roundtrip_cost_per_ounce": 0.4},
        "source_fingerprints": {
            "source_file_sha256": source, "git_revision_env": commit,
            "loaded_m1_bidask_sha256": m1,
        },
        "run_parameters": {**{k: v for k, v in spec.items() if k != "parameters"},
                           **spec["parameters"]},
        "trades": 6, "total_fees": 2.4, "net_pnl": sum(pnl),
        "months_observed": 6, "positive_months": 3,
        "nonpositive_months": 3, "forced_end_of_data_closures": 0,
    }
    (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    recorded = batch.audit_run(folder, spec, source, commit)
    manifest = {
        "schema": batch.SCHEMA, "plan_sha256": plan_sha,
        "source_sha256": source, "engine_commit": commit,
        "results": {"candidate-1": recorded},
    }
    result = screen.select(plan, manifest, tmp_path / "runs",
                           train_start="2024-01", train_end="2024-03",
                           review_start="2024-04", review_end="2024-06",
                           min_train_trades=3, min_positive_fraction=0.6)
    row = result["results"][0]
    assert row["training_screen"] == "PASSED_EXPLORATORY"
    assert row["train"]["net_pnl_usd_per_oz"] == 9
    assert row["later_review_descriptive_only"]["net_pnl_usd_per_oz"] == -6
    assert result["evidence_context"] == "HISTORICAL_EXPOSED_NOT_OOS_NOT_LIVE_APPROVED"
    # Data tampering is rejected by canonical re-audit before any ranking.
    (folder / "trades.csv").write_text("closed_at,net_pnl,cost\n", encoding="utf-8")
    try:
        screen.select(plan, manifest, tmp_path / "runs",
                      train_start="2024-01", train_end="2024-03",
                      review_start="2024-04", review_end="2024-06")
    except ValueError:
        pass
    else:
        raise AssertionError("Altered trade evidence passed canonical audit")
