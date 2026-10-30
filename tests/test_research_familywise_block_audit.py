"""Synthetic-only paired-block max audit contract tests."""
from __future__ import annotations

import numpy as np
import pytest
from scripts import research_familywise_block_audit as audit


def test_deterministic_and_no_zero_probability():
    x = np.array([[1., -1., 0.], [2., -2., 0.], [-1., 1., 0.]] * 8)
    first = audit.paired_block_max_test(x, ["alpha", "beta", "flat"],
                                        block_length=3, replicates=999, seed=7)
    second = audit.paired_block_max_test(x, ["alpha", "beta", "flat"],
                                         block_length=3, replicates=999, seed=7)
    assert first == second
    assert first["candidate_family_size"] == 3
    assert first["calendar_months"] == 24
    assert 1 / 1000 <= first["bootstrap"]["max_statistic_tail_fraction_exploratory"] <= 1
    assert "NOT_OOS" in first["evidence_context"]


def test_numeric_kernel_reports_only_supplied_month_matrix():
    x = np.arange(24, dtype=float).reshape(12, 2)
    original = audit.paired_block_max_test(x, ["a", "b"], block_length=2,
                                           replicates=999, seed=123)
    assert original["best_job_id"] == "b"
    assert original["best_total_training_net_usd_per_oz"] == sum(x[:, 1])
    assert original["best_positive_training_months"] == 12


def test_max_statistic_includes_losing_candidates_and_tie_is_stable():
    x = np.array([[1., 1., -10.]] * 12)
    out = audit.paired_block_max_test(x, ["a", "b", "loser"],
                                      block_length=1, replicates=999, seed=42)
    assert out["best_job_id"] == "a"
    assert out["candidate_family_size"] == 3
    assert out["bootstrap"]["max_statistic_tail_fraction_exploratory"] == .001


@pytest.mark.parametrize("matrix,ids", [
    (np.ones((11, 2)), ["a", "b"]),
    (np.ones((12, 0)), []),
    (np.ones((12, 2)), ["a", "a"]),
    (np.ones((12, 2)), ["a"]),
    (np.ones((12, 2)), ["a", None]),
    (np.full((12, 1), np.nan), ["a"]),
    (np.ones((12, 1), dtype=bool), ["a"]),
    (np.ones((12, 1), dtype=object), ["a"]),
])
def test_reject_invalid_universe(matrix, ids):
    with pytest.raises(ValueError):
        audit.paired_block_max_test(matrix, ids, block_length=3, replicates=999)


@pytest.mark.parametrize("kwargs", [
    {"block_length": 0}, {"block_length": 13},
    {"block_length": True}, {"replicates": 998},
    {"replicates": True}, {"replicates": 20001},
    {"seed": -1}, {"seed": True}, {"seed": 2**63},
])
def test_reject_invalid_bootstrap_controls(kwargs):
    options = {"block_length": 3, "replicates": 999, "seed": 1}
    options.update(kwargs)
    with pytest.raises(ValueError):
        audit.paired_block_max_test(np.ones((12, 1)), ["a"], **options)


def test_joint_resampling_preserves_perfectly_opposite_candidates():
    # Centered candidate vectors are exact negatives. With common month
    # indices the maxima must be >=0 for every bootstrap draw. A separate
    # resample per strategy would violate this paired-null property.
    x = np.column_stack((np.arange(12, dtype=float), -np.arange(12, dtype=float)))
    result = audit.paired_block_max_test(x, ["up", "down"],
                                         block_length=2, replicates=999, seed=12)
    assert result["bootstrap"]["null_max_mean_monthly_95pct_usd_per_oz"] >= 0


def test_incomplete_batch_is_rejected_before_computation(monkeypatch, tmp_path):
    plan = {"schema": "TEST", "dataset": str(tmp_path / "source"),
            "source_sha256": "a" * 64, "engine_commit": "b" * 40}
    (tmp_path / "source").write_bytes(b"fake")
    (tmp_path / "out").mkdir()
    manifest = {"schema": "TEST", "plan_sha256": "frozen",
                "source_sha256": "a" * 64, "engine_commit": "b" * 40,
                "results": {"a": {"status": "PASS"}}}
    monkeypatch.setattr(audit.batch, "read_strict_json", lambda path: plan if path == tmp_path / "plan.json" else manifest)
    monkeypatch.setattr(audit.batch, "expand", lambda _: ([{"id": "a", "spec": {}}, {"id": "b", "spec": {}}], "frozen"))
    monkeypatch.setattr(audit.batch, "file_sha", lambda _: "a" * 64)
    monkeypatch.setattr(audit.batch, "checkout_commit", lambda: "b" * 40)
    monkeypatch.setattr(audit.batch, "SCHEMA", "TEST")
    from contextlib import nullcontext
    monkeypatch.setattr(audit.batch, "exclusive_batch_lock", lambda _: nullcontext())
    with pytest.raises(ValueError, match="Incomplete"):
        audit.audit(tmp_path / "plan.json", tmp_path / "out",
                    train_start="2024-01", train_end="2024-12")


def test_bootstrap_matches_explicit_paired_block_reference():
    matrix = np.array([[float(i % 5 - 2), float(i % 7 - 3)]
                       for i in range(12)])
    seed, reps, block = 18, 999, 3
    out = audit.paired_block_max_test(matrix, ["a", "b"],
                                      block_length=block, replicates=reps, seed=seed)
    rng = np.random.default_rng(seed)
    centered = matrix - matrix.mean(axis=0)
    observed = float(matrix.mean(axis=0).max())
    maxima = []
    for _ in range(reps):
        starts = rng.integers(0, 12, size=4, dtype=np.int64)
        indices = [(int(start) + offset) % 12 for start in starts
                   for offset in range(block)]
        maxima.append(float(centered[indices].mean(axis=0).max()))
    assert out["bootstrap"]["exceedances"] == sum(v >= observed for v in maxima)
    assert out["bootstrap"]["null_max_mean_monthly_95pct_usd_per_oz"] == pytest.approx(
        float(np.quantile(maxima, .95)))


def test_complete_audited_batch_uses_every_candidate(monkeypatch, tmp_path):
    plan = {"schema": "TEST", "dataset": str(tmp_path / "source"),
            "source_sha256": "a" * 64, "engine_commit": "b" * 40}
    (tmp_path / "source").write_bytes(b"synthetic only")
    (tmp_path / "out").mkdir()
    manifest = {"schema": "TEST", "plan_sha256": "frozen",
                "source_sha256": "a" * 64, "engine_commit": "b" * 40,
                "results": {"a": {"status": "PASS"}, "b": {"status": "PASS"}}}
    months = [f"2024-{month:02d}" for month in range(1, 13)]
    written = []
    monkeypatch.setattr(audit.batch, "read_strict_json",
                        lambda path: plan if path == tmp_path / "plan.json" else manifest)
    monkeypatch.setattr(audit.batch, "expand",
                        lambda _: ([{"id": "a", "spec": {}}, {"id": "b", "spec": {}}], "frozen"))
    monkeypatch.setattr(audit.batch, "file_sha", lambda _: "a" * 64)
    monkeypatch.setattr(audit.batch, "checkout_commit", lambda: "b" * 40)
    monkeypatch.setattr(audit.batch, "SCHEMA", "TEST")
    monkeypatch.setattr(audit.batch, "PASSED", "PASS")
    from contextlib import nullcontext
    monkeypatch.setattr(audit.batch, "exclusive_batch_lock", lambda _: nullcontext())
    def fake_audit(folder, *args):
        return {**manifest["results"][folder.name],
                "monthly_net_pnl": dict.fromkeys(months, 1. if folder.name == "a" else -2.)}
    # The frozen manifest must contain the identical audited evidence.
    for ident in ("a", "b"):
        manifest["results"][ident] = {"status": "PASS",
            "monthly_net_pnl": dict.fromkeys(months, 1. if ident == "a" else -2.)}
    monkeypatch.setattr(audit.batch, "audit_run", fake_audit)
    monkeypatch.setattr(audit.batch, "atomic_manifest",
                        lambda path, result: written.append((path, result)))
    result = audit.audit(tmp_path / "plan.json", tmp_path / "out",
                         train_start="2024-01", train_end="2024-12",
                         block_length=3, replicates=999, seed=1)
    assert result["candidate_job_ids"] == ["a", "b"]
    assert result["best_job_id"] == "a"
    assert result["candidate_family_size"] == 2
    assert result["best_total_training_net_usd_per_oz"] == 12
    assert written[0][0].name == "familywise_block_audit.json"
