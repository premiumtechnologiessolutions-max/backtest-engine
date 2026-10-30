"""Frozen synthetic-evidence tests; never a historical Gold replay."""
from dataclasses import asdict
import json
import pytest

from norisk_quant.math_discovery import Formula
from scripts import research_campaign_attestation as cert
from scripts.run_arithmetic_evolution import run as generate
from scripts.materialize_arithmetic_generation import materialize


def _training():
    return {"schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
            "years": [2012, 2013], "explored_ids": [], "candidates": [{
                "formula": asdict(Formula()), "records": [{
                    "year": y, "metrics": {
                        "months": {f"{y}-{m:02d}": 1.0 for m in range(1, 13)},
                        "net_usd_per_oz": 12., "trades": 40, "fees_usd": 16.,
                        "positive_months": 12, "uncertain_gap_trades": 0,
                        "synthetic_forced_closures": 0, "accounting": "PASSED",
                    }} for y in (2012, 2013)],
            }]}


def test_immutable_campaign_intent_allows_resume_but_not_rewrite(tmp_path):
    root = tmp_path / "campaign"
    root.mkdir()
    source = tmp_path / "in.json"
    source.write_text(json.dumps(_training()))
    args = dict(seed=19, first_generation=1, proposal_count=2, shard_size=1)
    first = cert.freeze_campaign_intent(root, source, **args)
    assert first == cert.freeze_campaign_intent(root, source, **args)
    assert not first["independent_oos_proven"]
    before = (root / "campaign_intent.json").read_bytes()
    for altered in ({"seed": 20}, {"proposal_count": 3},
                    {"shard_size": 4}, {"first_generation": 2}):
        with pytest.raises(ValueError, match="Immutable campaign intent"):
            cert.freeze_campaign_intent(root, source, **(args | altered))
    assert (root / "campaign_intent.json").read_bytes() == before
    source.write_text(source.read_text() + " ")
    with pytest.raises(ValueError, match="Immutable campaign intent"):
        cert.freeze_campaign_intent(root, source, **args)


def test_tampered_or_symlinked_intent_refused(tmp_path):
    root = tmp_path / "campaign"
    root.mkdir()
    source = tmp_path / "in.json"
    source.write_text("{}")
    args = dict(seed=1, first_generation=1, proposal_count=1, shard_size=1)
    cert.freeze_campaign_intent(root, source, **args)
    plan = root / "campaign_intent.json"
    plan.write_text(plan.read_text().replace('"seed": 1', '"seed": 2'))
    with pytest.raises(ValueError, match="Immutable campaign intent"):
        cert.freeze_campaign_intent(root, source, **args)
    plan.unlink()
    plan.symlink_to(source)
    with pytest.raises(ValueError, match="Unsafe campaign intent"):
        cert.freeze_campaign_intent(root, source, **args)


@pytest.fixture
def generation(tmp_path, monkeypatch):
    source = tmp_path / "training.json"
    source.write_text(json.dumps(_training()))
    folder = tmp_path / "generation_0001"
    folder.mkdir()
    manifest = folder / "generation.json"
    generate(source, manifest, seed=17, generation=1, proposal_count=2)
    materialize(source, manifest, folder / "dispatch")
    shard = folder / "replay_2012_from_001_count_002"
    shard.mkdir()
    (folder / "next_training_input.json").write_text("{}")
    calls = []

    def fake_feedback(initial, manifest, dispatch, shards, output):
        calls.append((initial, manifest, dispatch, shards, output))
        return {"status": "COMPLETE_EXPOSED_TRAINING_FEEDBACK_NOT_OOS",
                "next_input_sha256": "f" * 64}

    monkeypatch.setattr(cert, "compile_feedback", fake_feedback)
    return source, folder, calls


def test_cached_generation_rechecks_exact_generation_and_dispatch(generation):
    source, folder, calls = generation
    result = cert.attest_cached_generation(
        source, folder, generation=1, seed=17, proposal_count=2)
    assert result["replay_shards_reaudited"] == 1
    assert result["next_input_sha256"] == "f" * 64
    assert len(calls) == 1
    for changed in ({"generation": 2}, {"seed": 18}, {"proposal_count": 1}):
        with pytest.raises(ValueError, match="different research controls"):
            cert.attest_cached_generation(
                source, folder, **({"generation": 1, "seed": 17,
                                    "proposal_count": 2} | changed))
    assert len(calls) == 1


def test_cached_generation_rejects_tampered_formula(generation):
    source, folder, calls = generation
    formula = next((folder / "dispatch").glob("formula_*.json"))
    formula.write_text("{}")
    with pytest.raises(ValueError, match="Existing evidence differs"):
        cert.attest_cached_generation(
            source, folder, generation=1, seed=17, proposal_count=2)
    assert calls == []


def test_cached_generation_refuses_missing_annual_replay(generation):
    source, folder, calls = generation
    next(folder.glob("replay_*")).rmdir()
    with pytest.raises(ValueError, match="no safe annual"):
        cert.attest_cached_generation(
            source, folder, generation=1, seed=17, proposal_count=2)
    assert calls == []
