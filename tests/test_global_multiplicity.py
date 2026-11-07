"""Global family diagnostics on fully synthetic exact fractions only."""
import copy
import math

import pytest

from norisk_quant.campaign_sharding import freeze_sharded_campaign
from norisk_quant.global_multiplicity import global_adjusted_diagnostics


def campaign(n=3):
    return freeze_sharded_campaign({
        "source_commit": "a" * 40,
        "dataset": {
            "id": "xauusd_m1", "archive_sha256": "b" * 64,
            "start": "2020-01-01", "end": "2026-01-01",
            "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2024-01-01", "end": "2024-12-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [
            {"id": f"test_hypothesis_{i:03d}",
             "code_sha256": "c" * 64, "spec_sha256": "d" * 64}
            for i in range(n)],
        "execution_engines": ["norisk_quant"],
        "ai_reviewers": [],
        "resource_limits": {"max_workers": 2, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.40,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })


def fractions():
    return {
        "test_hypothesis_000": [1, 100],
        "test_hypothesis_001": [1, 20],
        "test_hypothesis_002": [1, 2],
    }


def test_bonferroni_calculation_and_explicit_no_approval():
    out = global_adjusted_diagnostics(
        campaign(), fractions(), method="bonferroni")
    assert out["candidate_count"] == 3
    assert out["results"]["test_hypothesis_000"]["adjusted_nominal_p"] == pytest.approx(0.03)
    assert out["results"]["test_hypothesis_001"]["adjusted_nominal_p"] == pytest.approx(0.15)
    assert out["results"]["test_hypothesis_000"]["below_nominal_adjusted_alpha"] is True
    assert all(not row["strategy_approved"] for row in out["results"].values())
    assert out["research_results_accepted"] is False


def test_by_is_more_conservative_for_arbitrary_dependence():
    frozen = campaign()
    by = global_adjusted_diagnostics(frozen, fractions())
    bon = global_adjusted_diagnostics(
        frozen, fractions(), method="bonferroni")
    assert by["correction_method"] == "benjamini_yekutieli"
    assert by["harmonic_correction"] == pytest.approx(1 + .5 + 1 / 3)
    assert by["results"]["test_hypothesis_000"]["adjusted_nominal_p"] == pytest.approx(0.055)
    assert by["results"]["test_hypothesis_000"]["adjusted_nominal_p"] > bon["results"]["test_hypothesis_000"]["adjusted_nominal_p"]
    assert by["market_data_opened"] is False


def test_incomplete_or_extra_candidate_family_rejected():
    x = fractions()
    del x["test_hypothesis_001"]
    with pytest.raises(ValueError, match="All frozen"):
        global_adjusted_diagnostics(campaign(), x)
    x = fractions()
    x["unregistered_hypothesis"] = [1, 1000]
    with pytest.raises(ValueError, match="All frozen"):
        global_adjusted_diagnostics(campaign(), x)


@pytest.mark.parametrize("bad", [[True, 10], [1, 0], [-1, 10], [11, 10],
                                 [1, float("nan")], [1.0, 10], [1, 1000000001]])
def test_broken_exact_fractions_fail_closed(bad):
    x = fractions()
    x["test_hypothesis_000"] = bad
    with pytest.raises(ValueError):
        global_adjusted_diagnostics(campaign(), x)


def test_candidate_order_and_input_order_cannot_change_nominal_outcome():
    first = global_adjusted_diagnostics(campaign(), fractions())
    other = dict(reversed(list(fractions().items())))
    second = global_adjusted_diagnostics(campaign(), other)
    assert first == second


def test_cross_shard_family_uses_every_candidate_not_best_shard():
    frozen = campaign(35)
    assert frozen["shard_count"] == 2
    all_p = {f"test_hypothesis_{i:03d}": [1, 100]
             for i in range(35)}
    out = global_adjusted_diagnostics(
        frozen, all_p, method="bonferroni")
    assert out["candidate_count"] == 35
    assert out["results"]["test_hypothesis_000"]["adjusted_nominal_p"] == pytest.approx(0.35)
    assert out["execution_authorized"] is False


@pytest.mark.parametrize("alpha", [True, 0, 1, -0.3, float("nan")])
def test_invalid_alpha_denied(alpha):
    with pytest.raises(ValueError):
        global_adjusted_diagnostics(campaign(), fractions(), alpha=alpha)
