"""Matched training-only contrasts: synthetic evidence, no market edge claim."""
from dataclasses import asdict

import pytest

from norisk_quant.math_discovery import Formula
from norisk_quant.research_failure_hypotheses import analyze_matched_training_pairs


YEARS = (2012, 2013)


def candidate(formula, yearly_nets):
    return {
        "formula": asdict(formula),
        "records": [
            {"year": year, "metrics": {
                "months": {f"{year}-{m:02d}": yearly_nets[i] / 12.
                           for m in range(1, 13)},
                "net_usd_per_oz": yearly_nets[i],
                "trades": 40, "fees_usd": 16.0,
                "positive_months": 12 if yearly_nets[i] > 0 else 0,
                "uncertain_gap_trades": 0, "synthetic_forced_closures": 0,
                "accounting": "PASSED",
            }} for i, year in enumerate(YEARS)
        ],
    }


def test_one_field_pair_is_training_association_not_causal():
    first = candidate(Formula(), (-24., -12.))
    second = candidate(Formula(threshold=1.5), (12., 36.))
    result = analyze_matched_training_pairs([first, second], YEARS)
    assert result["total_single_parameter_pairs"] == 1
    row = result["contrasts"][0]
    assert row["changed_field"] == "threshold"
    assert row["training_net_delta_usd_per_oz"] == 84.0
    assert row["months_improved"] == 24
    assert row["months_worsened"] == 0
    assert row["consistent_positive_yearly_effect"] is True
    assert row["next_action"] == "PREREGISTER_A_NEW_COMPARISON"
    assert row["interpretation"] == "POST_HOC_TRAINING_ASSOCIATION_NOT_CAUSAL"
    assert row["independent_oos_proven"] is False
    assert result["live_trading_authorized"] is False


def test_result_invariant_to_candidate_order():
    first = candidate(Formula(), (-24., -12.))
    second = candidate(Formula(threshold=1.5), (12., 36.))
    assert (analyze_matched_training_pairs([first, second], YEARS) ==
            analyze_matched_training_pairs([second, first], YEARS))


def test_multiple_parameter_changes_are_not_matched():
    first = candidate(Formula(), (-24., -12.))
    other = candidate(Formula(threshold=1.5, stop_usd=50.), (12., 36.))
    assert (analyze_matched_training_pairs([first, other], YEARS)
            ["total_single_parameter_pairs"] == 0)


def test_improvement_in_only_one_year_is_not_promoted():
    first = candidate(Formula(), (-24., 30.))
    second = candidate(Formula(threshold=1.5), (24., 12.))
    row = analyze_matched_training_pairs([first, second], YEARS)["contrasts"][0]
    assert row["consistent_positive_yearly_effect"] is False
    assert row["next_action"] == "DO_NOT_PROMOTE_INCONSISTENT_TRAINING_CONTRAST"


def test_duplicate_and_noncanonical_holdout_fields_fail_closed():
    first = candidate(Formula(), (12., 12.))
    with pytest.raises(ValueError, match="Duplicate"):
        analyze_matched_training_pairs([first, first], YEARS)
    first["records"][0]["metrics"]["holdout_score"] = 123
    with pytest.raises(ValueError, match="canonical"):
        analyze_matched_training_pairs([first], YEARS)


@pytest.mark.parametrize("limit", [0, 1001, True])
def test_bounds_are_strict(limit):
    with pytest.raises(ValueError, match="bounded"):
        analyze_matched_training_pairs(
            [candidate(Formula(), (12., 12.))], YEARS, limit=limit)


def test_no_trade_profit_evidence_is_refused():
    first = candidate(Formula(), (12., 12.))
    first["records"][0]["metrics"]["trades"] = 0
    first["records"][0]["metrics"]["fees_usd"] = 0.
    with pytest.raises(ValueError, match="trade"):
        analyze_matched_training_pairs([first], YEARS)
