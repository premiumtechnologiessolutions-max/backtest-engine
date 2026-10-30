"""Synthetic only: no claim of statistically valid Gold strategy p-values."""
import pytest
from scripts.prospective_multiple_testing import holm_bonferroni


def test_holm_step_down_and_order_independence():
    sample = {"C": 0.04, "A": 0.001, "B": 0.02}
    expected = {"A": 0.003, "B": 0.04, "C": 0.04}
    for source in (sample, dict(reversed(list(sample.items())))):
        result = holm_bonferroni(source)
        assert {key: item["holm_adjusted_p"] for key, item in result.items()} == pytest.approx(expected)
        assert all(item["reject"] for item in result.values())


def test_holm_rejection_is_step_down_not_independent_thresholds():
    result = holm_bonferroni({"a": 0.01, "b": 0.03, "c": 0.04})
    assert result["a"]["reject"] is True
    assert result["b"]["reject"] is False
    assert result["c"]["reject"] is False


@pytest.mark.parametrize("values", [{}, {"a": float("nan")}, {"a": float("inf")},
                                    {"a": -0.1}, {"a": 1.1}, {"a": True},
                                    {"": 0.01}, {"a": 0.01, "b": None}])
def test_bad_family_fails_closed(values):
    with pytest.raises(ValueError):
        holm_bonferroni(values)


@pytest.mark.parametrize("alpha", [0, 1, True, float("nan"), float("inf"), -0.1])
def test_bad_alpha_fails_closed(alpha):
    with pytest.raises(ValueError):
        holm_bonferroni({"a": 0.01}, alpha)


def test_equal_p_values_are_deterministic_and_monotonic():
    result = holm_bonferroni({"z": 0.01, "a": 0.01, "m": 0.01})
    assert list(result) == ["a", "m", "z"]
    assert all(v["holm_adjusted_p"] == pytest.approx(0.03) for v in result.values())
