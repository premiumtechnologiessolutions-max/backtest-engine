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
def prepared(tmp_path):
    source = tmp_path / "training.json"
    generation = tmp_path / "generation.json"
    source.write_text(json.dumps(_training()))
    run(source, generation, seed=17, generation=1, proposal_count=3)
    archive = tmp_path / "Gold data.zip"
    archive.write_bytes(b"fixture-not-a-market-archive")
    digest = sha256(archive.read_bytes()).hexdigest()
    return source, generation, tmp_path / "dispatch", archive, digest, tmp_path / "out"


def _fake_cli(command, *, check, capture_output, text, tamper=False):
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
        "trades": 1, "net_pnl": -0.4, "total_fees": 0.4,
        "positive_months": 0, "months_observed": 12,
        "max_drawdown_observed_m1": 0.4,
        "last_observed_equity": -0.4, "last_observed_realized_pnl": -0.4,
        "accounting_checks": {"status": "PASSED"},
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
        "gross_pnl": 0.0, "cost": 0.4, "net_pnl": -0.4,
        "exit_reason": "end_of_data", "gap_minutes": 0,
    }
    pd.DataFrame([trade]).to_csv(target / "trades.csv", index=False)
    pd.DataFrame({"period": [f"2012-{m:02d}" for m in range(1, 13)],
                  "net_pnl": [-0.4] + [0.0] * 11}).to_csv(
        target / "monthly.csv", index=False)
    pd.DataFrame({"period": ["2012-01-01"], "net_pnl": [-0.4]}).to_csv(
        target / "weekly.csv", index=False)
    pd.DataFrame({"time": ["2012-01-01T00:02:00Z"],
                  "equity": [-0.4]}).to_csv(target / "equity_m1.csv", index=False)
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
    with pytest.raises(ValueError, match="SHA mismatch"):
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
