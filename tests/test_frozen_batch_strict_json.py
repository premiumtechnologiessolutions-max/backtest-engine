"""Synthetic-only fail-closed JSON contract for frozen research artifacts.

These tests do NOT run the original Gold ZIP, broker execution, or OOS research.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import research_batch_orchestrator as lab


@pytest.mark.parametrize("payload", [
    '{"schema":1,"schema":1}',
    '{"settings":{"fee":0.40,"fee":0.40}}',
    '{"results":[{"status":"ok","status":"ok"}]}',
])
def test_duplicate_keys_rejected_at_every_depth(tmp_path, payload):
    path = tmp_path / "evidence.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate research JSON key"):
        lab.read_strict_json(path)


@pytest.mark.parametrize("payload", [
    '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}',
    '{"x":1e999}', '{"x":-1e999}', '{"nested":[{"cost":1e309}]}',
])
def test_nonstandard_nonfinite_json_rejected(tmp_path, payload):
    path = tmp_path / "evidence.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="Nonfinite research JSON"):
        lab.read_strict_json(path)


@pytest.mark.parametrize("payload", ['{', '{"a":1,}', '\ufeff{"a":1}'])
def test_malformed_json_rejected(tmp_path, payload):
    path = tmp_path / "evidence.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed research JSON"):
        lab.read_strict_json(path)


def test_valid_nested_json_unchanged(tmp_path):
    data = {"settings": {"fee": 0.4}, "results": [{"a": 1}], "enabled": True}
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert lab.read_strict_json(path) == data


def test_symlinked_json_refused(tmp_path):
    original = tmp_path / "original.json"
    original.write_text("{}", encoding="utf-8")
    link = tmp_path / "evidence.json"
    link.symlink_to(original)
    with pytest.raises(ValueError, match="unsafe research JSON"):
        lab.read_strict_json(link)


def test_missing_json_refused(tmp_path):
    with pytest.raises(ValueError, match="unsafe research JSON"):
        lab.read_strict_json(tmp_path / "missing.json")


@pytest.mark.parametrize("payload", [
    '{"execution":"x","execution":"x"}',
    '{"settings":{"roundtrip_cost_per_ounce":0.4,"roundtrip_cost_per_ounce":0.4}}',
    '{"settings":{"roundtrip_cost_per_ounce":NaN}}',
])
def test_audit_run_refuses_ambiguous_summary_before_csv(tmp_path, payload):
    folder = tmp_path / "job"
    folder.mkdir()
    (folder / "summary.json").write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate|Nonfinite"):
        lab.audit_run(folder, {}, "a" * 64, "b" * 40)


def test_resumed_batch_refuses_duplicate_manifest_before_launch(tmp_path, monkeypatch):
    raw = b"synthetic test bytes, not market data"
    dataset = tmp_path / "synthetic.zip"
    dataset.write_bytes(raw)
    commit = "b" * 40
    plan = {
        "schema": lab.SCHEMA, "dataset": str(dataset),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "engine_commit": commit, "exposure_context": "historical_exposed",
        "jobs": [{
            "id": "test-ema", "strategy": "ema", "timeframe": "M15",
            "execution": "fast", "start": "2024-01-01", "end": "2024-01-31",
            "parameters": {"fast": 9, "slow": 21},
        }], "grids": [],
    }
    monkeypatch.setattr(lab, "checkout_commit", lambda: commit)
    out = tmp_path / "out"
    out.mkdir()
    (out / "batch_manifest.json").write_text(
        '{"schema":"NRFX_FROZEN_BATCH_V1","schema":"NRFX_FROZEN_BATCH_V1"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate research JSON key"):
        lab.run_plan(plan, out)
    assert not (out / "runs").exists()


def test_cli_refuses_ambiguous_plan_before_running(tmp_path, monkeypatch):
    plan = tmp_path / "plan.json"
    plan.write_text('{"jobs":[],"jobs":[]}', encoding="utf-8")
    def forbidden(*args, **kwargs):
        raise AssertionError("run_plan must not be invoked")
    monkeypatch.setattr(lab, "run_plan", forbidden)
    with pytest.raises(ValueError, match="Duplicate research JSON key"):
        lab.main(["--plan", str(plan), "--out", str(tmp_path / "out")])


def test_finite_large_exponent_remains_valid(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text('{"cost":1e308,"tiny":1e-100}', encoding="utf-8")
    evidence = lab.read_strict_json(path)
    assert evidence["cost"] == 1e308
    assert evidence["tiny"] == 1e-100


@pytest.mark.parametrize("payload", [
    '{"settings":{"roundtrip_cost_per_ounce":1e999}}',
    '{"settings":{"roundtrip_cost_per_ounce":-1e999}}',
])
def test_summary_rejects_overflow_before_csv(tmp_path, payload):
    folder = tmp_path / "job"
    folder.mkdir()
    (folder / "summary.json").write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="Nonfinite research JSON"):
        lab.audit_run(folder, {}, "a" * 64, "b" * 40)
