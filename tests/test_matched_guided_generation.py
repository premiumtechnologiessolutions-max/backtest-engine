"""Synthetic-only deterministic matched-hypothesis policy regression.

No market data is read; no trading edge or independent OOS is asserted.
"""
from dataclasses import asdict
import json

import pytest

from norisk_quant.math_discovery import Formula
from norisk_quant.research_evolution import evolve_training_generation
from scripts.run_arithmetic_evolution import run
from scripts.materialize_arithmetic_generation import materialize
from scripts.research_campaign_attestation import freeze_campaign_intent

YEARS = (2012, 2013)


def candidate(formula, annual):
    return {"formula": asdict(formula), "records": [{
        "year": year, "metrics": {
            "months": {f"{year}-{month:02d}": annual / 12
                       for month in range(1, 13)},
            "net_usd_per_oz": annual, "trades": 45, "fees_usd": 18.,
            "positive_months": 12 if annual > 0 else 0,
            "uncertain_gap_trades": 0, "synthetic_forced_closures": 0,
            "accounting": "PASSED",
        }} for year in YEARS]}


def pairs():
    return [candidate(Formula(), -12.),
            candidate(Formula(threshold=1.5), 12.)]


def test_guided_one_field_hypothesis_and_diversity_budget():
    r = evolve_training_generation(pairs(), YEARS, seed=17, generation=7,
                                   proposal_count=4, proposal_policy="matched_guided_v1")
    assert r["planning_diagnostics"] == {
        "matched_training_pairs": 1, "guided_proposals": 1,
        "diversity_proposals": 3,
        "evidence_scope": "POST_HOC_EXPOSED_TRAINING_ONLY_NOT_OOS"}
    guided = [p for p in r["proposals"] if p["proposal_basis"] ==
              "POST_HOC_MATCHED_TRAINING_HYPOTHESIS"]
    assert len(guided) == 1
    assert guided[0]["mutated_fields"] == ["threshold"]
    assert len(guided[0]["source_contrast_sha256"]) == 64
    assert guided[0]["parent_identity"] == Formula(threshold=1.5).identity()
    assert len(set(p["identity"] for p in r["proposals"])) == 4
    assert r["independent_oos_proven"] is False
    assert r["live_trading_authorized"] is False


def test_guided_deterministic_under_shuffling_and_explored_history():
    opts = dict(seed=17, generation=7, proposal_count=4,
                proposal_policy="matched_guided_v1")
    a = evolve_training_generation(pairs(), YEARS, **opts)
    assert a == evolve_training_generation(pairs()[::-1], YEARS, **opts)
    explored = tuple(p["identity"] for p in a["proposals"])
    b = evolve_training_generation(pairs(), YEARS, explored_ids=explored, **opts)
    assert not set(explored).intersection(p["identity"] for p in b["proposals"])


def test_legacy_policy_keeps_historical_manifest_exact():
    kwargs = dict(seed=17, generation=7, proposal_count=4)
    a = evolve_training_generation(pairs(), YEARS, **kwargs)
    b = evolve_training_generation(pairs(), YEARS, proposal_policy="legacy_random",
                                   **kwargs)
    assert a == b
    assert "proposal_policy" not in a
    assert "planning_diagnostics" not in a
    assert all("proposal_basis" not in p for p in a["proposals"])


def test_guided_manifest_rechecked_and_tampering_blocked(tmp_path):
    source = tmp_path / "training.json"
    source.write_text(json.dumps({
        "schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
        "years": list(YEARS), "candidates": pairs(), "explored_ids": []}))
    manifest = tmp_path / "generation.json"
    run(source, manifest, seed=17, generation=7, proposal_count=4,
        proposal_policy="matched_guided_v1")
    first = materialize(source, manifest, tmp_path / "dispatch")
    assert first["formula_count"] == 4
    assert materialize(source, manifest, tmp_path / "dispatch") == first
    tampered = json.loads(manifest.read_text())
    tampered["result"]["planning_diagnostics"]["guided_proposals"] = 99
    manifest.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="deterministic training replay"):
        materialize(source, manifest, tmp_path / "dispatch")


def test_opt_in_campaign_policy_frozen_before_reuse(tmp_path):
    source = tmp_path / "training.json"
    source.write_text(json.dumps({
        "schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
        "years": list(YEARS), "candidates": pairs(), "explored_ids": []}))
    root = tmp_path / "campaign"
    root.mkdir()
    kwargs = dict(seed=17, first_generation=7, proposal_count=4, shard_size=2)
    frozen = freeze_campaign_intent(root, source, proposal_policy="matched_guided_v1",
                                    **kwargs)
    assert frozen["proposal_policy"] == "matched_guided_v1"
    assert frozen == freeze_campaign_intent(
        root, source, proposal_policy="matched_guided_v1", **kwargs)
    with pytest.raises(ValueError, match="Immutable campaign intent differs"):
        freeze_campaign_intent(root, source, proposal_policy="legacy_random", **kwargs)


def test_unknown_policy_and_leaked_holdout_fail_closed():
    with pytest.raises(ValueError, match="Unknown frozen proposal policy"):
        evolve_training_generation(pairs(), YEARS, seed=1, generation=1,
                                   proposal_policy="random")
    rows = pairs()
    rows[0]["records"][0]["metrics"]["future_oos_net"] = 1000000.
    with pytest.raises(ValueError, match="Unexpected or incomplete training record"):
        evolve_training_generation(rows, YEARS, seed=1, generation=1,
                                   proposal_policy="matched_guided_v1")


def test_without_valid_matched_pair_fallback_is_explicit():
    r = evolve_training_generation([candidate(Formula(), 12.)], YEARS,
                                   seed=8, generation=1, proposal_count=3,
                                   proposal_policy="matched_guided_v1")
    assert r["planning_diagnostics"]["guided_proposals"] == 0
    assert r["planning_diagnostics"]["diversity_proposals"] == 3
    assert all(p["proposal_basis"] == "BASELINE_DIVERSITY_MUTATION"
               for p in r["proposals"])
