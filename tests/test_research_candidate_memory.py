"""Synthetic accounting fixtures for training-only bounded evolutionary memory."""
from dataclasses import asdict
from itertools import product

import pytest

from norisk_quant.math_discovery import Formula
from norisk_quant.research_candidate_memory import select_training_memory


YEARS = (2012, 2013)


def _candidate(index: int, *, losing: bool = False):
    # 160 distinct, canonical, valid formula identities.
    lookback, feature_a, threshold = list(product(
        (5, 8, 10, 12, 15, 20, 30, 45),
        (0, 1, 2, 3, 4),
        (0.5, 1., 1.5, 2.0)))[index]
    formula = asdict(Formula(lookback=lookback, feature_a=feature_a,
                             threshold=threshold))
    monthly = -1.0 if losing else 1.0
    records = [{"year": year, "metrics": {
        "months": {f"{year}-{month:02d}": monthly
                   for month in range(1, 13)},
        "net_usd_per_oz": 12 * monthly,
        "trades": 40, "fees_usd": 16.0,
        "positive_months": 0 if losing else 12,
        "uncertain_gap_trades": 0, "synthetic_forced_closures": 0,
        "accounting": "PASSED",
    }} for year in YEARS]
    return {"formula": formula, "records": records}


def test_lifetime_160_candidates_compacts_to_128_without_forgetting_explored():
    candidates = [_candidate(i, losing=i < 32) for i in range(160)]
    outcome = select_training_memory(candidates, YEARS)
    assert outcome["universe_size"] == 160
    assert outcome["active_size"] == 128
    assert outcome["evicted_count"] == 32
    assert len(set(outcome["all_identities"])) == 160
    assert all(x["training_score"] >= outcome["evicted"][0]["training_score"]
               for x in outcome["selected"])
    assert all("NONPOSITIVE_TRAINING_NET" in x["failure_reasons"]
               for x in outcome["evicted"])
    assert outcome["independent_oos_proven"] is False
    assert outcome["live_trading_authorized"] is False


def test_order_independent_selection_and_audit():
    candidates = [_candidate(i) for i in range(132)]
    first = select_training_memory(candidates, YEARS)
    second = select_training_memory(candidates[::-1], YEARS)
    assert first["all_identities"] == second["all_identities"]
    assert [r["identity"] for r in first["selected"]] == [
        r["identity"] for r in second["selected"]]
    assert first["evicted"] == second["evicted"]


def test_reject_duplicate_formula_identity():
    with pytest.raises(ValueError, match="Duplicate"):
        select_training_memory([_candidate(0), _candidate(0)], YEARS)


def test_reject_evidence_with_holdout_or_noncanonical_metrics():
    candidate = _candidate(0)
    candidate["records"][0]["metrics"]["holdout_profit"] = 10.0
    with pytest.raises(ValueError, match="frozen training"):
        select_training_memory([candidate], YEARS)


def test_reject_incomplete_training_year():
    candidate = _candidate(0)
    candidate["records"].pop()
    with pytest.raises(ValueError, match="training years"):
        select_training_memory([candidate], YEARS)


def test_reject_invalid_bounds_and_zero_active():
    with pytest.raises(ValueError, match="bounded"):
        select_training_memory([], YEARS)
    with pytest.raises(ValueError, match="bounded"):
        select_training_memory([_candidate(0)], YEARS, limit=129)
    with pytest.raises(ValueError, match="bounded"):
        select_training_memory([_candidate(0)] * 257, YEARS)


def test_failure_categories_do_not_claim_future_proof():
    outcome = select_training_memory([_candidate(0, losing=True)], YEARS)
    line = outcome["selected"][0]
    assert "NONPOSITIVE_TRAINING_NET" in line["failure_reasons"]
    assert "NONPOSITIVE_TRAINING_YEAR" in line["failure_reasons"]
    assert line["independent_oos_proven"] is False
