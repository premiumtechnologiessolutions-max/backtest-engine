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


@pytest.mark.parametrize("shifted_exit", [
    "2024-02-02T12:00:00+00:00",  # different month, same total net P/L
    "2024-01-08T12:00:00+00:00",  # different W-SUN week, same month
    "2024-01-02T12:00:00",        # timezone-naive exit
])
def test_audit_rejects_period_shift_despite_matching_total_pnl(tmp_path, shifted_exit):
    folder = tmp_path / "job"
    make_report(folder)
    path = folder / "trades.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["closed_at"] = shifted_exit
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    assert sum(float(row["net_pnl"]) for row in rows) == pytest.approx(1)
    with pytest.raises(ValueError, match="exit allocation|timestamp"):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)


@pytest.mark.parametrize("ledger", ["monthly", "weekly", "trades"])
def test_duplicate_csv_header_is_rejected_even_when_values_match(tmp_path, ledger):
    folder = tmp_path / "job"
    make_report(folder)
    path = folder / (ledger + ".csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    # DictReader previously silently selected one of two identical columns.
    lines[0] += ",net_pnl"
    lines[1:] = [line + "," + line.split(",")[1] for line in lines[1:]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate or invalid"):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)


@pytest.mark.parametrize("ledger", ["monthly", "weekly", "trades"])
def test_extra_csv_cell_is_rejected(tmp_path, ledger):
    folder = tmp_path / "job"
    make_report(folder)
    path = folder / (ledger + ".csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] += ",unexpected"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Ragged"):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)


@pytest.mark.parametrize("ledger", ["monthly", "weekly", "trades"])
def test_missing_csv_cell_is_rejected(tmp_path, ledger):
    folder = tmp_path / "job"
    make_report(folder)
    path = folder / (ledger + ".csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].rsplit(",", 1)[0]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Ragged"):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)


@pytest.mark.parametrize("ledger", ["monthly", "weekly", "trades"])
def test_symlinked_csv_is_rejected(tmp_path, ledger):
    folder = tmp_path / "job"
    make_report(folder)
    path = folder / (ledger + ".csv")
    original = folder / (ledger + ".original")
    path.rename(original)
    path.symlink_to(original)
    with pytest.raises(ValueError, match="unsafe"):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)


@pytest.mark.parametrize("unsafe", ["symlink", "missing"])
def test_summary_json_must_be_regular_file(tmp_path, unsafe):
    folder = tmp_path / "job"
    make_report(folder)
    summary = folder / "summary.json"
    if unsafe == "symlink":
        original = folder / "summary.original"
        summary.rename(original)
        summary.symlink_to(original)
    else:
        summary.unlink()
    with pytest.raises(ValueError, match="unsafe summary JSON"):
        lab.audit_run(folder, spec(), SOURCE, COMMIT)


@pytest.mark.parametrize("target", ["manifest", "run_dir"])
def test_batch_refuses_symlinked_evidence_paths(tmp_path, monkeypatch, target):
    raw = b"synthetic test bytes, not real market data"
    dataset = tmp_path / "gold-private.zip"
    dataset.write_bytes(raw)
    p = plan(tmp_path)
    p["source_sha256"] = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(lab, "checkout_commit", lambda: COMMIT)
    out = tmp_path / "output"
    out.mkdir()
    outside = tmp_path / "outside"
    if target == "manifest":
        outside.write_text("do not read or overwrite", encoding="utf-8")
        (out / "batch_manifest.json").symlink_to(outside)
        expected = "Unsafe batch manifest symlink"
    else:
        outside.mkdir()
        (out / "runs").mkdir()
        (out / "runs" / "test-ema").symlink_to(outside, target_is_directory=True)
        expected = "Unsafe experiment directory symlink"
    with pytest.raises(ValueError, match=expected):
        lab.run_plan(p, out)
    if target == "manifest":
        assert outside.read_text(encoding="utf-8") == "do not read or overwrite"
    else:
        assert list(outside.iterdir()) == []


# Batch output locking and durable manifest tests are synthetic-only.
def test_batch_output_lock_blocks_second_process_and_releases(tmp_path):
    out = tmp_path / "runs"
    out.mkdir()
    with lab.exclusive_batch_lock(out):
        with pytest.raises(ValueError, match="already running"):
            with lab.exclusive_batch_lock(out):
                pass
    with lab.exclusive_batch_lock(out):
        assert (out / ".research_batch.lock").stat().st_size == 0


def test_batch_output_lock_released_after_exception(tmp_path):
    out = tmp_path / "runs"
    out.mkdir()
    with pytest.raises(RuntimeError, match="synthetic crash"):
        with lab.exclusive_batch_lock(out):
            raise RuntimeError("synthetic crash")
    with lab.exclusive_batch_lock(out):
        pass


@pytest.mark.parametrize("attack", ["symlink", "hardlink", "permissive", "nonempty", "directory"])
def test_batch_output_lock_rejects_unsafe_existing_inode(tmp_path, attack):
    out = tmp_path / "runs"
    out.mkdir()
    lock = out / ".research_batch.lock"
    outside = tmp_path / "untouched"
    outside.write_text("keep", encoding="utf-8")
    if attack == "symlink":
        lock.symlink_to(outside)
    elif attack == "hardlink":
        import os
        os.link(outside, lock)
    elif attack == "permissive":
        lock.write_bytes(b"")
        lock.chmod(0o644)
    elif attack == "nonempty":
        lock.write_text("not an empty lock", encoding="utf-8")
    else:
        lock.mkdir()
    with pytest.raises((ValueError, OSError)):
        with lab.exclusive_batch_lock(out):
            pass
    assert outside.read_text(encoding="utf-8") == "keep"


def test_batch_lock_detects_inode_replacement_during_acquisition(tmp_path, monkeypatch):
    if lab.fcntl is None:
        pytest.skip("POSIX only")
    out = tmp_path / "runs"
    out.mkdir()
    real_flock = lab.fcntl.flock

    def replaced(fd, mode):
        real_flock(fd, mode)
        if mode & lab.fcntl.LOCK_EX:
            (out / ".research_batch.lock").unlink()
            (out / ".research_batch.lock").write_bytes(b"")

    monkeypatch.setattr(lab.fcntl, "flock", replaced)
    with pytest.raises(ValueError, match="path changed"):
        with lab.exclusive_batch_lock(out):
            pass


def test_atomic_manifest_rejects_symlink_and_keeps_external_file(tmp_path):
    target = tmp_path / "batch_manifest.json"
    outside = tmp_path / "private"
    outside.write_text("keep", encoding="utf-8")
    target.symlink_to(outside)
    with pytest.raises(ValueError, match="Unsafe batch manifest"):
        lab.atomic_manifest(target, {"test": "synthetic"})
    assert outside.read_text(encoding="utf-8") == "keep"


def test_atomic_manifest_preserves_previous_version_on_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "batch_manifest.json"
    lab.atomic_manifest(target, {"phase": "first"})
    previous = target.read_bytes()
    def fail_replace(*args):
        raise OSError("synthetic disk failure")
    monkeypatch.setattr(lab.os, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic disk failure"):
        lab.atomic_manifest(target, {"phase": "second"})
    assert target.read_bytes() == previous
    assert not list(tmp_path.glob(".batch-manifest-*.tmp"))


def test_atomic_manifest_writes_private_file_and_no_staging_residue(tmp_path):
    target = tmp_path / "batch_manifest.json"
    lab.atomic_manifest(target, {"monthly_pnl": None, "status": "NOT_EXECUTED"})
    assert json.loads(target.read_text())["monthly_pnl"] is None
    assert target.stat().st_mode & 0o077 == 0
    assert not list(tmp_path.glob(".batch-manifest-*.tmp"))


def test_real_batch_run_holds_output_lock_through_canonical_execution(tmp_path, monkeypatch):
    data = tmp_path / "private-synthetic.zip"
    data.write_bytes(b"synthetic test archive")
    p = plan(tmp_path)
    p["dataset"] = str(data)
    p["source_sha256"] = lab.file_sha(data)
    monkeypatch.setattr(lab, "checkout_commit", lambda: COMMIT)
    calls = []
    def fake_engine(command, **kwargs):
        calls.append(command)
        out = Path(command[command.index("--out") + 1])
        with pytest.raises(ValueError, match="already running"):
            with lab.exclusive_batch_lock(tmp_path / "output"):
                pass
        make_report(out, source=p["source_sha256"])
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(lab.subprocess, "run", fake_engine)
    result = lab.run_plan(p, tmp_path / "output", max_jobs=1)
    assert result["executed_this_invocation"] == 1
    assert len(calls) == 1


def test_same_frozen_spec_with_different_job_ids_is_rejected(tmp_path):
    p = plan(tmp_path, jobs=[
        {"id": "first", **spec()},
        {"id": "second", **spec()},
    ])
    with pytest.raises(ValueError, match="Duplicate frozen strategy specification"):
        lab.expand(p)


def test_duplicate_spec_across_explicit_job_and_grid_is_rejected(tmp_path):
    p = plan(tmp_path, grids=[{
        "id_prefix": "same-spec", "strategy": "ema", "timeframe": "M15",
        "execution": "fast", "start": "2024-01-01", "end": "2024-02-29",
        "grid": {"fast": [9], "slow": [21], "stop_atr": [1.5], "rr": [2.0]},
    }])
    with pytest.raises(ValueError, match="Duplicate frozen strategy specification"):
        lab.expand(p)


def test_duplicate_spec_across_distinct_grid_prefixes_is_rejected(tmp_path):
    grid = {
        "strategy": "ema", "timeframe": "M15", "execution": "fast",
        "start": "2024-01-01", "end": "2024-02-29",
        "grid": {"fast": [8], "slow": [24]},
    }
    p = plan(tmp_path, jobs=[], grids=[
        {"id_prefix": "grid-a", **grid},
        {"id_prefix": "grid-b", **grid},
    ])
    with pytest.raises(ValueError, match="Duplicate frozen strategy specification"):
        lab.expand(p)


def test_batch_index_is_private_after_reconciled_execution(tmp_path, monkeypatch):
    import os
    data = tmp_path / "private-synthetic.zip"
    data.write_bytes(b"synthetic data only")
    p = plan(tmp_path)
    p["dataset"] = str(data)
    p["source_sha256"] = lab.file_sha(data)
    monkeypatch.setattr(lab, "checkout_commit", lambda: COMMIT)

    def fake_engine(command, **kwargs):
        folder = Path(command[command.index("--out") + 1])
        make_report(folder, source=p["source_sha256"])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lab.subprocess, "run", fake_engine)
    out = tmp_path / "out"
    assert lab.run_plan(p, out)["reconciled_jobs"] == 1
    index = out / "research_batch_index.html"
    assert "2024-01" in index.read_text(encoding="utf-8")
    if os.name == "posix":
        assert index.stat().st_mode & 0o077 == 0


def test_batch_index_symlink_cannot_overwrite_external_file(tmp_path, monkeypatch):
    data = tmp_path / "private-synthetic.zip"
    data.write_bytes(b"synthetic data only")
    p = plan(tmp_path)
    p["dataset"] = str(data)
    p["source_sha256"] = lab.file_sha(data)
    monkeypatch.setattr(lab, "checkout_commit", lambda: COMMIT)

    def fake_engine(command, **kwargs):
        folder = Path(command[command.index("--out") + 1])
        make_report(folder, source=p["source_sha256"])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lab.subprocess, "run", fake_engine)
    out = tmp_path / "out"
    out.mkdir()
    external = tmp_path / "external-private.txt"
    external.write_text("KEEP", encoding="utf-8")
    (out / "research_batch_index.html").symlink_to(external)
    with pytest.raises(ValueError, match="symlinked export destination"):
        lab.run_plan(p, out)
    assert external.read_text(encoding="utf-8") == "KEEP"


@pytest.mark.parametrize("field,bound", [
    ("start", "2024-01-03"),  # existing 2024-01-02 exit predates requested start
    ("end", "2024-02-05"),    # existing 2024-02-06 exit exceeds requested end
])
def test_audit_rejects_within_month_exit_outside_frozen_date_window(tmp_path, field, bound):
    folder = tmp_path / "job"
    make_report(folder)
    summary_path = folder / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["run_parameters"][field] = bound
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    declared = spec(**{field: bound})
    with pytest.raises(ValueError, match="outside frozen UTC research window"):
        lab.audit_run(folder, declared, SOURCE, COMMIT)


def _orphan_fixture(tmp_path, monkeypatch):
    data = tmp_path / "synthetic-private.zip"
    data.write_bytes(b"synthetic fixture only")
    frozen = plan(tmp_path)
    frozen["dataset"] = str(data)
    frozen["source_sha256"] = lab.file_sha(data)
    monkeypatch.setattr(lab, "checkout_commit", lambda: COMMIT)
    output = tmp_path / "batch"
    folder = output / "runs" / "test-ema"
    make_report(folder, source=frozen["source_sha256"])
    return frozen, output, folder


def test_opt_in_reconciles_completed_orphan_without_rerunning(tmp_path, monkeypatch):
    frozen, output, folder = _orphan_fixture(tmp_path, monkeypatch)

    def no_engine(*args, **kwargs):
        pytest.fail("A verified orphan must not trigger a duplicate backtest")

    monkeypatch.setattr(lab.subprocess, "run", no_engine)
    with pytest.raises(ValueError, match="Unknown existing run"):
        lab.run_plan(frozen, output)
    assert not (output / "batch_manifest.json").exists()
    result = lab.run_plan(frozen, output, recover_verified_orphans=True)
    assert result["executed_this_invocation"] == 0
    assert result["recovered_verified_orphans"] == 1
    record = lab.read_strict_json(output / "batch_manifest.json")["results"]["test-ema"]
    assert record == lab.audit_run(folder, spec(), frozen["source_sha256"], COMMIT)
    repeat = lab.run_plan(frozen, output, recover_verified_orphans=True)
    assert repeat["recovered_verified_orphans"] == 0
    assert repeat["executed_this_invocation"] == 0


@pytest.mark.parametrize("corruption", ["missing_weekly", "wrong_source", "altered_fees"])
def test_orphan_recovery_rejects_incomplete_or_tampered_evidence(
        tmp_path, monkeypatch, corruption):
    frozen, output, folder = _orphan_fixture(tmp_path, monkeypatch)
    if corruption == "missing_weekly":
        (folder / "weekly.csv").unlink()
    elif corruption == "wrong_source":
        summary_path = folder / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["source_fingerprints"]["source_file_sha256"] = SOURCE
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
    else:
        summary_path = folder / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["settings"]["roundtrip_cost_per_ounce"] = 0.39
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
    monkeypatch.setattr(
        lab.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("Never run an unverified orphan"))
    with pytest.raises(ValueError, match="Orphaned run failed canonical evidence audit"):
        lab.run_plan(frozen, output, recover_verified_orphans=True)
    assert not (output / "batch_manifest.json").exists()


def test_recovery_rejects_symlinked_runs_root(tmp_path, monkeypatch):
    frozen, output, _ = _orphan_fixture(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    (output / "runs" / "test-ema").rename(outside / "test-ema")
    (output / "runs").rmdir()
    (output / "runs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Unsafe research runs directory"):
        lab.run_plan(frozen, output, recover_verified_orphans=True)
    assert not (output / "batch_manifest.json").exists()


def test_orphan_recovery_requires_explicit_boolean(tmp_path):
    with pytest.raises(ValueError, match="flag must be boolean"):
        lab.run_plan(plan(tmp_path), tmp_path / "out",
                     recover_verified_orphans="yes", dry_run=True)
