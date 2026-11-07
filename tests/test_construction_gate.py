"""Synthetic-only tests: never run real market research."""
import copy
import pytest
from scripts.construction_gate import CHECKS, evaluate


def fixture():
    sha = "a" * 40
    return {"source_commit": sha, "checks": {
        name: {"passed": True, "artifact": f"tests/{name}.json", "source_commit": sha}
        for name in CHECKS}}


def test_complete_gate_does_not_certify_market_or_production():
    result = evaluate(fixture())
    assert result["engineering_gate_passed"] is True
    assert result["profitability_verified"] is False
    assert result["production_approved"] is False
    assert result["real_data_backtests_performed"] is False
    assert len(result["evidence_fingerprint"]) == 64


def test_missing_check_fails_closed():
    data = fixture()
    del data["checks"][CHECKS[0]]
    with pytest.raises(ValueError):
        evaluate(data)


@pytest.mark.parametrize("path", [
    "docs/../../secret", "https://bad.test", "tests/./x",
    "tests//x", "/tmp/x",
])
def test_unsafe_evidence_path_rejected(path):
    data = fixture()
    data["checks"][CHECKS[0]]["artifact"] = path
    with pytest.raises(ValueError):
        evaluate(data)


def test_commit_mismatch_rejected():
    data = fixture()
    data["checks"][CHECKS[0]]["source_commit"] = "b" * 40
    with pytest.raises(ValueError):
        evaluate(data)


def test_partial_gate_reports_missing_without_readiness():
    data = fixture()
    data["checks"][CHECKS[0]]["passed"] = False
    result = evaluate(data)
    assert result["passed"] == len(CHECKS) - 1
    assert result["missing"] == [CHECKS[0]]
    assert result["engineering_gate_passed"] is False


def test_boolean_or_unknown_check_rejected():
    data = fixture()
    data["checks"][CHECKS[0]]["passed"] = 1
    with pytest.raises(ValueError):
        evaluate(data)
    data = fixture()
    data["checks"]["extra"] = copy.deepcopy(data["checks"][CHECKS[0]])
    with pytest.raises(ValueError):
        evaluate(data)
