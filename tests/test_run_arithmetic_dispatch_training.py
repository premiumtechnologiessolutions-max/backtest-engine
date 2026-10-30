"""Contract tests for canonical training-only Reference/Fast dispatch replay."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from norisk_quant.math_discovery import Formula
from scripts.run_arithmetic_evolution import run
from scripts.run_arithmetic_dispatch_training import execute


def _training():
    return {
        "schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
        "years": [2012, 2013], "explored_ids": [],
        "candidates": [{
            "formula": asdict(Formula()),
            "records": [{
                "year": year,
                "metrics": {
                    "months": {f"{year}-{month:02d}": 1.0
                               for month in range(1, 13)},
                    "net_usd_per_oz": 12.0, "trades": 45,
                    "fees_usd": 18.0, "positive_months": 12,
                    "uncertain_gap_trades": 0,
                    "synthetic_forced_closures": 0, "accounting": "PASSED",
                },
            } for year in (2012, 2013)],
        }],
    }


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    source = tmp_path / "training.json"
    generation = tmp_path / "generation.json"
    source.write_text(json.dumps(_training()))
    run(source, generation, seed=17, generation=1, proposal_count=3)
    archive = tmp_path / "Gold data.zip"
    archive.write_bytes(b"fixture-not-a-market-archive")
    digest = sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.SOURCE_SHA", digest)
    return source, generation, tmp_path / "dispatch", archive, digest, tmp_path / "out"


def _fake_cli(command, *, check, capture_output, text, tamper=False,
              corrupt_both=False, monthly_corruption=None,
              weekly_corruption=None, equity_corruption=None):
    assert check and capture_output and text
    assert command[:3] == [__import__("sys").executable, "-m", "norisk_quant.cli"]
    assert "--strategy" in command and command[command.index("--strategy") + 1] == "arithmetic"
    assert command[command.index("--all-in-cost-per-ounce") + 1] == "0.40"
    engine = command[command.index("--execution") + 1]
    formula = Formula(**json.loads(Path(
        command[command.index("--formula-json") + 1]).read_text()))
    target = Path(command[command.index("--out") + 1])
    target.mkdir(parents=True)
    summary = {
        "run_parameters": {
            "execution": engine, "strategy": "arithmetic",
            "timeframe": "M1", "arithmetic_formula_sha256": formula.identity(),
            "all_in_cost_per_ounce": 0.40, "ounces": 1.0,
        },
        "source_fingerprints": {"loaded_m1_bidask_sha256": "a" * 64},
        "months_with_m1_observations": 12,
        "start_utc": "2012-01-01T00:00:00+00:00",
        "end_utc": "2012-12-31T23:59:00+00:00",
        "trades": 1, "net_pnl": -0.4, "total_fees": 0.4,
        "positive_months": 0, "months_observed": 12,
        "max_drawdown_observed_m1": 0.4,
        "last_observed_equity": -0.4, "last_observed_realized_pnl": -0.4,
        "accounting_checks": "PASSED",
        "forced_end_of_data_closures": 0,
        "same_entry_bar_target_deferred": 0,
        "trades_exposed_to_uncertain_gaps": 0,
    }
    (target / "summary.json").write_text(json.dumps(summary))
    trade = {
        "strategy": "arithmetic_" + formula.identity()[:16],
        "signal_at": "2012-01-01T00:00:00+00:00",
        "entry_at": "2012-01-01T00:01:00+00:00",
        "closed_at": "2012-01-01T00:02:00+00:00",
        "side": 1, "entry_price": 100.0,
        "exit_price": 100.1 if tamper and engine == "fast" else 100.0,
        "stop": 99.0, "target": 102.0, "ounces": 1.0,
        "gross_pnl": 0.1 if corrupt_both else 0.0,
        "cost": 0.4, "net_pnl": -0.4,
        "exit_reason": "end_of_data", "gap_minutes": 0,
    }
    pd.DataFrame([trade]).to_csv(target / "trades.csv", index=False)
    monthly = pd.DataFrame({
        "period": [f"2012-{m:02d}" for m in range(1, 13)],
        "net_pnl": [-0.4] + [0.0] * 11,
        "total_cost": [0.4] + [0.0] * 11,
        "trades": [1] + [0] * 11,
        "wins": [0] * 12,
    })
    if monthly_corruption == "offsetting_net":
        monthly.loc[0, "net_pnl"] = -0.2
        monthly.loc[1, "net_pnl"] = -0.2
    elif monthly_corruption == "missing_zero_month":
        monthly = monthly.drop(index=1)
    elif monthly_corruption == "duplicate_month":
        monthly.loc[1, "period"] = "2012-01"
    elif monthly_corruption == "wrong_fee":
        monthly.loc[0, "total_cost"] = 0.3
    elif monthly_corruption == "wrong_trade_count":
        monthly.loc[0, "trades"] = 0
    elif monthly_corruption == "wrong_wins":
        monthly.loc[0, "wins"] = 1
    monthly.to_csv(target / "monthly.csv", index=False)
    weeks = pd.period_range("2012-01-01", "2012-12-31", freq="W-SUN")
    weekly = pd.DataFrame({
        "period": [str(week) for week in weeks],
        "net_pnl": [-0.4] + [0.0] * (len(weeks) - 1),
        "total_cost": [0.4] + [0.0] * (len(weeks) - 1),
        "trades": [1] + [0] * (len(weeks) - 1),
        "wins": [0] * len(weeks),
    })
    if weekly_corruption == "offsetting_net":
        weekly.loc[0, "net_pnl"] = -0.2
        weekly.loc[1, "net_pnl"] = -0.2
    elif weekly_corruption == "missing_zero_week":
        weekly = weekly.drop(index=1)
    elif weekly_corruption == "duplicate_week":
        weekly.loc[1, "period"] = weekly.loc[0, "period"]
    elif weekly_corruption == "wrong_fee":
        weekly.loc[0, "total_cost"] = 0.3
    elif weekly_corruption == "wrong_trade_count":
        weekly.loc[0, "trades"] = 0
    elif weekly_corruption == "wrong_wins":
        weekly.loc[0, "wins"] = 1
    weekly.to_csv(target / "weekly.csv", index=False)
    # Synthetic observed marks span all 12 months; gaps are NOT filled.
    observed = (["2012-01-01T00:00:00Z", "2012-01-01T00:01:00Z",
                 "2012-01-01T00:02:00Z"]
                + [f"2012-{month:02d}-01T00:00:00Z" for month in range(2, 12)]
                + ["2012-12-31T23:59:00Z"])
    equity = pd.DataFrame({
        "at": observed,
        "realized_pnl": [0.0, 0.0] + [-0.4] * (len(observed) - 2),
        "floating_pnl": [0.0] * len(observed),
        "equity": [0.0, 0.0] + [-0.4] * (len(observed) - 2),
        "drawdown": [0.0, 0.0] + [0.4] * (len(observed) - 2),
    })
    if equity_corruption == "wrong_drawdown":
        equity.loc[1, "drawdown"] = 0.2
    elif equity_corruption == "shift_realized":
        equity.loc[1, "realized_pnl"] = -0.2
        equity.loc[1, "equity"] = -0.2
        equity.loc[1, "drawdown"] = 0.2
    elif equity_corruption == "duplicate_minute":
        equity = pd.concat([equity.iloc[:2], equity.iloc[[1]], equity.iloc[2:]],
                           ignore_index=True)
    elif equity_corruption == "missing_exit_mark":
        equity = equity.drop(index=2)
    elif equity_corruption == "missing_entry_mark":
        equity = equity.drop(index=1)
    elif equity_corruption == "wrong_summary_dd":
        summary["max_drawdown_observed_m1"] = 0.3
        (target / "summary.json").write_text(json.dumps(summary))
    elif equity_corruption == "wrong_last_equity":
        equity.loc[equity.index[-1], "equity"] = -0.3
        equity.loc[equity.index[-1], "realized_pnl"] = -0.3
    equity.to_csv(target / "equity_m1.csv", index=False)
    pd.DataFrame(columns=["gap_start", "gap_end"]).to_csv(
        target / "gap_catalogue.csv", index=False)


def test_real_dispatch_replay_and_idempotent_frozen_evidence(prepared, monkeypatch):
    source, generation, dispatch, archive, digest, out = prepared
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        _fake_cli(command, **kwargs)
    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.subprocess.run",
                        fake_run)
    result = execute(source, generation, dispatch, archive, digest, 2012, out,
                     start_ordinal=2, limit=2)
    assert result["completed"] == 2
    assert result["training_only"] is True
    assert result["independent_oos_proven"] is False
    assert result["live_trading_authorized"] is False
    assert len(calls) == 4
    assert json.loads((out / "training_replay_index.json").read_text()) == result
    assert all(r["reference_fast_parity"] == "PASSED" for r in result["results"])
    with pytest.raises(ValueError, match="already exists"):
        execute(source, generation, dispatch, archive, digest, 2012, out)


def test_price_mismatch_never_publishes_partial_batch(prepared, monkeypatch):
    source, generation, dispatch, archive, digest, out = prepared
    def fake_run(command, **kwargs):
        _fake_cli(command, tamper=True, **kwargs)
    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.subprocess.run",
                        fake_run)
    with pytest.raises(ValueError, match="trades.csv mismatch"):
        execute(source, generation, dispatch, archive, digest, 2012, out,
                limit=1)
    assert not out.exists()
    assert not list(out.parent.glob(".nrfx_arithmetic_training_*"))


def test_holdout_year_and_archive_sha_are_rejected(prepared, monkeypatch):
    source, generation, dispatch, archive, digest, out = prepared
    def forbidden(*args, **kwargs):
        pytest.fail("Canonical backtest must not run on rejected input")
    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.subprocess.run",
                        forbidden)
    with pytest.raises(ValueError, match="SHA"):
        execute(source, generation, dispatch, archive, "0" * 64, 2012, out)
    with pytest.raises(ValueError, match="holdout replay forbidden"):
        execute(source, generation, dispatch, archive, digest, 2024, out)
    assert not out.exists()


def test_tampered_dispatch_and_output_symlink_rejected(prepared, tmp_path):
    source, generation, dispatch, archive, digest, out = prepared
    from scripts.materialize_arithmetic_generation import materialize
    manifest = materialize(source, generation, dispatch)
    formula = dispatch / manifest["formulas"][0]["relative_path"]
    formula.write_text('{"lookback": 5}')
    with pytest.raises(ValueError, match="differs"):
        execute(source, generation, dispatch, archive, digest, 2012, out)
    assert not out.exists()
    formula.unlink()
    materialize(source, generation, dispatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    out.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        execute(source, generation, dispatch, archive, digest, 2012, out)
    assert not list(outside.iterdir())


def test_shared_execution_accounting_corruption_is_not_certified(prepared, monkeypatch):
    source, generation, dispatch, archive, digest, out = prepared
    def fake_run(command, **kwargs):
        _fake_cli(command, corrupt_both=True, **kwargs)
    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.subprocess.run",
                        fake_run)
    with pytest.raises(ValueError, match="gross/net/fee arithmetic"):
        execute(source, generation, dispatch, archive, digest, 2012, out,
                limit=1)
    assert not out.exists()


def test_out_of_range_ordinals_and_noninteger_year_rejected(prepared, monkeypatch):
    source, generation, dispatch, archive, digest, out = prepared
    def forbidden(*args, **kwargs):
        pytest.fail("Rejected research request must never invoke the CLI")
    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.subprocess.run",
                        forbidden)
    with pytest.raises(ValueError, match="ordinal exceeds"):
        execute(source, generation, dispatch, archive, digest, 2012, out,
                start_ordinal=4, limit=1)
    with pytest.raises(ValueError, match="Invalid bounded"):
        execute(source, generation, dispatch, archive, digest, True, out)
    assert not out.exists()


@pytest.mark.parametrize("corruption", [
    "offsetting_net", "missing_zero_month", "duplicate_month",
    "wrong_fee", "wrong_trade_count", "wrong_wins",
])
def test_same_corruption_in_both_engines_cannot_fake_monthly_stability(
        prepared, monkeypatch, corruption):
    source, generation, dispatch, archive, digest, out = prepared

    def fake_run(command, **kwargs):
        _fake_cli(command, monthly_corruption=corruption, **kwargs)

    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.subprocess.run",
                        fake_run)
    with pytest.raises(ValueError, match="Monthly ledger"):
        execute(source, generation, dispatch, archive, digest, 2012, out,
                limit=1)
    assert not out.exists()
    assert not list(out.parent.glob(".nrfx_arithmetic_training_*"))


@pytest.mark.parametrize("corruption", [
    "offsetting_net", "missing_zero_week", "duplicate_week",
    "wrong_fee", "wrong_trade_count", "wrong_wins",
])
def test_identical_weekly_corruption_in_both_engines_is_rejected(
        prepared, monkeypatch, corruption):
    source, generation, dispatch, archive, digest, out = prepared

    def fake_run(command, **kwargs):
        _fake_cli(command, weekly_corruption=corruption, **kwargs)

    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.subprocess.run",
                        fake_run)
    with pytest.raises(ValueError, match="Weekly ledger"):
        execute(source, generation, dispatch, archive, digest, 2012, out,
                limit=1)
    assert not out.exists()
    assert not list(out.parent.glob(".nrfx_arithmetic_training_*"))


@pytest.mark.parametrize("corruption", [
    "wrong_drawdown", "shift_realized", "duplicate_minute",
    "missing_exit_mark", "missing_entry_mark",
    "wrong_summary_dd", "wrong_last_equity",
])
def test_identical_m1_equity_corruption_in_both_engines_is_rejected(
        prepared, monkeypatch, corruption):
    source, generation, dispatch, archive, digest, out = prepared

    def fake_run(command, **kwargs):
        _fake_cli(command, equity_corruption=corruption, **kwargs)

    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.subprocess.run",
                        fake_run)
    with pytest.raises(ValueError, match="M1 equity"):
        execute(source, generation, dispatch, archive, digest, 2012, out,
                limit=1)
    assert not out.exists()
    assert not list(out.parent.glob(".nrfx_arithmetic_training_*"))


@pytest.mark.parametrize("corruption", [
    "accounting_failed", "accounting_object", "bad_bidask_fingerprint",
    "negative_forced_count", "excess_gap_count", "noninteger_trades",
])
def test_identical_invalid_canonical_summary_is_not_certified(
        prepared, monkeypatch, corruption):
    """Both engines can agree on invalid evidence; agreement is insufficient."""
    source, generation, dispatch, archive, digest, out = prepared

    def fake_run(command, **kwargs):
        _fake_cli(command, **kwargs)
        target = Path(command[command.index("--out") + 1])
        summary_path = target / "summary.json"
        summary = json.loads(summary_path.read_text())
        if corruption == "accounting_failed":
            summary["accounting_checks"] = "FAILED"
        elif corruption == "accounting_object":
            summary["accounting_checks"] = {"status": "PASSED"}
        elif corruption == "bad_bidask_fingerprint":
            summary["source_fingerprints"]["loaded_m1_bidask_sha256"] = "not-a-sha"
        elif corruption == "negative_forced_count":
            summary["forced_end_of_data_closures"] = -1
        elif corruption == "excess_gap_count":
            summary["trades_exposed_to_uncertain_gaps"] = 2
        elif corruption == "noninteger_trades":
            summary["trades"] = 1.0
        summary_path.write_text(json.dumps(summary))

    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.subprocess.run",
                        fake_run)
    with pytest.raises(ValueError, match=(
            "accounting|fingerprint|count|trade count")):
        execute(source, generation, dispatch, archive, digest, 2012, out,
                limit=1)
    assert not out.exists()
    assert not list(out.parent.glob(".nrfx_arithmetic_training_*"))

@pytest.mark.parametrize("corruption,expected", [
    ("shared_wrong_strategy", "Trade strategy identity mismatch"),
    ("fast_changed_coverage", "summary mismatch: start_utc"),
    ("fast_changed_run_parameters", "run parameters differ"),
])
def test_replay_cannot_certify_wrong_strategy_or_divergent_run_contract(
        prepared, monkeypatch, corruption, expected):
    """Identical ledgers are not enough to prove candidate/parameter provenance."""
    source, generation, dispatch, archive, digest, out = prepared

    def fake_run(command, **kwargs):
        _fake_cli(command, **kwargs)
        target = Path(command[command.index("--out") + 1])
        engine = command[command.index("--execution") + 1]
        if corruption == "shared_wrong_strategy":
            ledger = target / "trades.csv"
            trades = pd.read_csv(ledger)
            trades.loc[:, "strategy"] = "arithmetic_other_candidate"
            trades.to_csv(ledger, index=False)
        elif engine == "fast":
            path = target / "summary.json"
            summary = json.loads(path.read_text())
            if corruption == "fast_changed_coverage":
                summary["start_utc"] = "2012-01-02T00:00:00+00:00"
            elif corruption == "fast_changed_run_parameters":
                summary["run_parameters"]["unapproved_setting"] = 1
            path.write_text(json.dumps(summary))

    monkeypatch.setattr("scripts.run_arithmetic_dispatch_training.subprocess.run",
                        fake_run)
    with pytest.raises(ValueError, match=expected):
        execute(source, generation, dispatch, archive, digest, 2012, out,
                limit=1)
    assert not out.exists()
    assert not list(out.parent.glob(".nrfx_arithmetic_training_*"))
