"""Synthetic-only bounded planner capacity and scope regression."""
from dataclasses import asdict
import json

import pytest

from norisk_quant.math_discovery import Formula
from scripts.benchmark_guided_planner_synthetic import benchmark


@pytest.fixture
def source(tmp_path):
    years = [2012, 2013]
    candidates = []
    for formula in (Formula(), Formula(threshold=1.5)):
        annual = -12. if formula.threshold == 1 else 12.
        candidates.append({
            "formula": asdict(formula),
            "records": [{"year": y, "metrics": {
                "months": {f"{y}-{m:02d}": annual / 12
                           for m in range(1, 13)},
                "net_usd_per_oz": annual, "trades": 45, "fees_usd": 18.,
                "positive_months": 12 if annual > 0 else 0,
                "uncertain_gap_trades": 0,
                "synthetic_forced_closures": 0,
                "accounting": "PASSED",
            }} for y in years],
        })
    path = tmp_path / "training.json"
    path.write_text(json.dumps({
        "schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
        "years": years, "candidates": candidates, "explored_ids": []}))
    return path


def test_capacity_plan_produces_unique_hypotheses_without_market_runs(source):
    result = benchmark(source, generations=6, per_generation=8)
    assert result["proof_type"] == "SYNTHETIC_GENERATION_ONLY_NO_BACKTEST"
    assert result["new_unique_formulas"] == 48
    assert result["total_explored_identities"] == 50
    assert result["active_parents"] == 50
    assert result["guided_proposals"] <= 48
    assert result["independent_oos_proven"] is False
    assert result["live_trading_authorized"] is False


@pytest.mark.parametrize("kwargs", [
    {"generations": 0}, {"generations": 201},
    {"generations": True}, {"per_generation": 33},
    {"per_generation": 0}, {"per_generation": True},
])
def test_unbounded_computational_budget_rejected(source, kwargs):
    with pytest.raises(ValueError, match="Bounded"):
        benchmark(source, **kwargs)


def test_untrusted_holdout_evidence_rejected_before_generation(source):
    raw = json.loads(source.read_text())
    raw["candidates"][0]["records"][0]["metrics"]["oos_winnings"] = 1e6
    source.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="frozen training"):
        benchmark(source, generations=1, per_generation=2)
