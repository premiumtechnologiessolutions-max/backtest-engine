"""Synthetic-only orchestration tests; never claims Gold ZIP or broker validation."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import research_batch_orchestrator as lab


SOURCE = "a" * 64
COMMIT = "b" * 40
M1 = "c" * 64


def spec(*, start="2024-01-01", end="2024-02-29", **kwargs):
    return {
        "strategy": "ema", "timeframe": "M15", "execution": "fast",
        "start": start, "end": end,
        "parameters": {"fast": 9, "slow": 21, "stop_atr": 1.5, "rr": 2.0},
        **kwargs,
    }


def plan(tmp_path, *, jobs=None, grids=None):
    return {
        "schema": lab.SCHEMA,
        "dataset": str(tmp_path / "gold-private.zip"),
        "source_sha256": SOURCE, "engine_commit": COMMIT,
        "exposure_context": "historical_exposed",
        "jobs": [{"id": "test-ema", **spec()}] if jobs is None else jobs,
        "grids": [] if grids is None else grids,
    }


def make_report(folder: Path, source=SOURCE, commit=COMMIT, *, outcome=(3.0, -2.0)):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "monthly.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "period", "net_pnl", "trades", "total_cost", "observed_m1_samples",
            "uncertain_gap_trades", "synthetic_end_of_data_trades",
        ])
        writer.writeheader()
        for month, pnl in zip(("2024-01", "2024-02"), outcome):
            writer.writerow({
                "period": month, "net_pnl": pnl, "trades": 2,
                "total_cost": "0.8", "observed_m1_samples": 100,
                "uncertain_gap_trades": 0, "synthetic_end_of_data_trades": 0,
            })
    with (folder / "weekly.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["period", "net_pnl", "trades", "total_cost"])
        writer.writeheader()
        for week, gain in zip(("2024-01-01/2024-01-07", "2024-02-05/2024-02-11"), outcome):
            writer.writerow({"period": week, "net_pnl": gain,
                             "trades": 2, "total_cost": 0.8})
    with (folder / "trades.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["net_pnl", "cost", "closed_at"])
        writer.writeheader()
        for stamp, gain in zip(("2024-01-02T12:00:00+00:00", "2024-02-06T12:00:00+00:00"), outcome):
            for _ in range(2):
                writer.writerow({"net_pnl": gain / 2, "cost": 0.4,
                                 "closed_at": stamp})
    summary = {
        "execution": "synthetic_same_reference_bid_ohlc_fixed_all_in_fee",
        "settings": {"roundtrip_cost_per_ounce": 0.4},
        "source_fingerprints": {
            "source_file_sha256": source, "git_revision_env": commit,
            "loaded_m1_bidask_sha256": M1,
        },
        "run_parameters": {**{k: v for k, v in spec().items() if k != "parameters"}, **spec()["parameters"]},
        "trades": 4, "total_fees": 1.6,
        "net_pnl": sum(outcome), "months_observed": 2,
        "positive_months": sum(v > 0 for v in outcome),
        "nonpositive_months": sum(v <= 0 for v in outcome),
        "forced_end_of_data_closures": 0,
    }
    (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")


def test_frozen_plan_and_stable_grid_expansion(tmp_path):
    p = plan(tmp_path, grids=[{
        "id_prefix": "ema-grid", "strategy": "ema", "timeframe": "M15",
        "execution": "fast", "start": "2024-01-01", "end": "2024-02-29",
        "grid": {"fast": [7, 9], "slow": [21, 30], "rr": [1.5, 2.0]},
    }])
    one, digest = lab.expand(p)
    two, again = lab.expand(p)
    assert (one, digest) == (two, again)
    assert len(one) == 9
    assert len({job["id"] for job in one}) == len(one)
    assert all(lab.JOB_ID.fullmatch(item["id"]) for item in one)


@pytest.mark.parametrize("bad", [
    {"fast": True}, {"fast": 4.5}, {"fast": 30}, {"stop_atr": 0},
    {"rr": float("nan")}, {"rr": float("inf")}, {"rr": "2"},
    {"inject": 1}, {"stop_atr": -1},
])
def test_rejects_invalid_or_unbounded_cli_specifications(bad):
    s = spec()
    s["parameters"].update(bad)
    with pytest.raises(ValueError):
        lab.check_spec(s)


@pytest.mark.parametrize("change", [
    {"strategy": "fake"}, {"timeframe": "M60"}, {"execution": "live"},
    {"start": "2024-03-01"}, {"end": "2023-12-31"},
])
def test_rejects_invalid_base_strategy_fields(change):
    s = spec(**change)
    with pytest.raises(ValueError):
        lab.check_spec(s)


def test_refuses_negative_bos_cost_filter():
    s = {"strategy": "bos-fib", "timeframe": "M1", "execution": "reference",
         "start": "2024-01-01", "end": "2024-01-31",
         "parameters": {"bos_min_gross_reward_fee_multiple": -0.5}}
    with pytest.raises(ValueError):
        lab.check_spec(s)


def test_rejects_forward_oos_assertion_and_relative_dataset(tmp_path):
    p = plan(tmp_path)
    p["exposure_context"] = "future_prospective"
    with pytest.raises(ValueError):
        lab.expand(p)
    p["exposure_context"] = "historical_exposed"
    p["dataset"] = "relative/gold.zip"
    with pytest.raises(ValueError):
        lab.expand(p)


def test_duplicate_jobs_refused(tmp_path):
    p = plan(tmp_path)
    p["jobs"].append(p["jobs"][0].copy())
    with pytest.raises(ValueError):
        lab.expand(p)


def test_grid_limit_blocks_unbounded_parameter_search(tmp_path):
    p = plan(tmp_path, jobs=[], grids=[{
        "id_prefix": "many", "strategy": "ema", "timeframe": "M15",
        "execution": "fast", "start": "2024-01-01", "end": "2024-02-29",
        "grid": {"fast": list(range(1, 40)), "slow": list(range(41, 81))},
    }])
    with pytest.raises(ValueError):
        lab.expand(p, limit=1000)


@pytest.mark.parametrize("name", ["../../escape", "x y", ".hidden", "Test-U", "a/" ])
def test_invalid_job_path_component_refused(tmp_path, name):
    p = plan(tmp_path, jobs=[{"id": name, **spec()}])
    with pytest.raises(ValueError):
        lab.expand(p)


def test_monthly_accounting_is_reconciled_from_real_report_structure(tmp_path):
    folder = tmp_path / "job"
    make_report(folder)
    result = lab.audit_run(folder, spec(), SOURCE, COMMIT)
    assert result["status"] == lab.PASSED
    assert result["monthly_net_pnl"] == {"2024-01": 3, "2024-02": -2}
    assert result["positive_months"] == 1
    assert result["trades"] == 4
    assert result["total_cost"] == 1.6
    assert result["summary_sha256"] == lab.file_sha(folder / "summary.json")
    assert result["weekly_sha256"] == lab.file_sha(folder / "weekly.csv")
    assert result["trades_sha256"] == lab.file_sha(folder / "trades.csv")


@pytest.mark.parametrize("mutation", [
    ("summary", "net_pnl", 900),
    ("summary", "trades", 99),
    ("summary", "positive_months", 2),
    ("summary", "forced_end_of_data_closures", 1),
    ("summary", "execution", "broker_tick_live"),
    ("provenance", "git_revision_env", "0" * 40),
    ("provenance", "source_file_sha256", "0" * 64),
    ("parameters", "strategy", "donchian"),
    ("settings", "roundtrip_cost_per_ounce", 0),
    ("monthly", "net_pnl", "1e309"),
    ("monthly", "observed_m1_samples", 0),
    ("monthly", "period", "2024-04"),
    ("weekly", "net_pnl", "600"),
    ("trades", "cost", "2"),
])
def test_broken_report_fails_closed(tmp_path, mutation):
    folder = tmp_path / "job"
    make_report(folder)
    section, key, value = mutation
    if section in ("monthly", "weekly", "trades"):
        path = folder / (section + ".csv")
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        rows[0][key] = value
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
    else:
        path = folder / "summary.json"
        summary = json.loads(path.read_text(encoding="utf-8"))
        target = {
            "summary": summary, "provenance": summary["source_fingerprints"],
            "parameters": summary["run_parameters"], "settings": summary["settings"],
        }[section]
        target[key] = value
        path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)


def test_month_without_observed_data_is_not_a_valid_return(tmp_path):
    folder = tmp_path / "job"
    make_report(folder)
    path = folder / "monthly.csv"
    data = path.read_text(encoding="utf-8").replace(",100,", ",0,", 1)
    path.write_text(data, encoding="utf-8")
    with pytest.raises(ValueError):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)


def test_dry_run_never_accesses_archive_or_launches_backtests(tmp_path):
    p = plan(tmp_path)
    result = lab.run_plan(p, tmp_path / "output", dry_run=True)
    assert result["status"] == "DEFINED_ONLY_NO_BACKTEST"
    assert result["jobs"] == 1
    assert not (tmp_path / "output").exists()


def test_batch_produces_reconciled_manifest_and_resumes_without_reexecution(tmp_path, monkeypatch):
    raw = b"synthetic fake zip for tests only"
    data = tmp_path / "gold-private.zip"
    data.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    p = plan(tmp_path)
    p["source_sha256"] = digest
    monkeypatch.setattr(lab, "checkout_commit", lambda: COMMIT)
    calls = []

    def fake_engine(command, **kwargs):
        calls.append(command)
        assert command[0] == lab.sys.executable
        assert kwargs["env"]["GITHUB_SHA"] == COMMIT
        assert "--all-in-cost-per-ounce" in command
        out = Path(command[command.index("--out") + 1])
        make_report(out, source=digest)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lab.subprocess, "run", fake_engine)
    out = tmp_path / "private-reports"
    first = lab.run_plan(p, out, max_jobs=1)
    assert first["executed_this_invocation"] == 1
    assert first["reconciled_jobs"] == 1
    assert len(calls) == 1
    assert "2024-01" in (out / "research_batch_index.html").read_text()
    second = lab.run_plan(p, out, max_jobs=1)
    assert second["executed_this_invocation"] == 0
    assert len(calls) == 1
    with (out / "runs" / "test-ema" / "monthly.csv").open("a") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="modified"):
        lab.run_plan(p, out)


def test_wrong_original_archive_is_rejected_without_invoking_engine(tmp_path, monkeypatch):
    data = tmp_path / "gold-private.zip"
    data.write_bytes(b"not-the-expected-bytes")
    p = plan(tmp_path)
    monkeypatch.setattr(lab, "checkout_commit", lambda: COMMIT)
    with pytest.raises(ValueError, match="SHA256"):
        lab.run_plan(p, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_failed_backtest_never_marked_passed(tmp_path, monkeypatch):
    data = tmp_path / "gold-private.zip"
    data.write_bytes(b"synthetic")
    p = plan(tmp_path)
    p["source_sha256"] = lab.file_sha(data)
    monkeypatch.setattr(lab, "checkout_commit", lambda: COMMIT)

    def crash(*args, **kwargs):
        raise lab.subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(lab.subprocess, "run", crash)
    with pytest.raises(RuntimeError):
        lab.run_plan(p, tmp_path / "out")
    manifest = json.loads((tmp_path / "out" / "batch_manifest.json").read_text())
    assert manifest["results"]["test-ema"]["status"] == "FAILED_REQUIRES_INVESTIGATION"


def test_manual_html_shows_only_recorded_monthly_values():
    html = lab.render_index({
        "results": {
            "test-ema": {
                "status": lab.PASSED, "monthly_net_pnl": {"2024-01": 3, "2024-02": -2},
            },
            "other": {"status": "FAILED_REQUIRES_INVESTIGATION"},
        },
    })
    assert "+3.00" in html and "-2.00" in html
    assert "NOT independent OOS" in html
    assert "monthly.csv" in html
    assert "No Risk FX" in html


def test_large_pnl_drift_is_not_hidden_by_relative_tolerance():
    # Prior relative comparison allowed a $0.10 discrepancy at $1bn P/L.
    assert not lab.same(1_000_000_000.0, 1_000_000_000.10)
    assert lab.same(100.0, 100.0000005)


def test_compensating_individual_trade_fees_are_rejected(tmp_path):
    folder = tmp_path / "job"
    make_report(folder)
    path = folder / "trades.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["cost"] = "0.2"
    rows[1]["cost"] = "0.6"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    assert sum(float(row["cost"]) for row in rows) == pytest.approx(1.6)
    with pytest.raises(ValueError, match="Individual trade fee"):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)


def test_noncanonical_nearby_transaction_cost_is_rejected(tmp_path):
    folder = tmp_path / "job"
    make_report(folder)
    path = folder / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["settings"]["roundtrip_cost_per_ounce"] = 0.4000001
    path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="transaction cost"):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)


@pytest.mark.parametrize("field", ["uncertain_gap_trades", "synthetic_end_of_data_trades"])
def test_impossible_exposure_counts_cannot_exceed_trade_count(tmp_path, field):
    folder = tmp_path / "job"
    make_report(folder)
    path = folder / "monthly.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0][field] = "5"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="counts exceed executed trades"):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)
