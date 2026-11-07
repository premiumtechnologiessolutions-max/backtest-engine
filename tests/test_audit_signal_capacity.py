"""Synthetic regression checks for conservative one-fill-per-signal feasibility."""
import pandas as pd
import pytest

from scripts.audit_signal_capacity import SignalCapacityError, audit_signal_capacity


def _frame(a=39, b=29):
    return pd.DataFrame({
        "id": ["a_0", "a_1", "b_0", "b_1"],
        "rule": ["a", "a", "b", "b"],
        "stop": [1, 2, 1, 2],
        "signals": [a, a, b, b],
        "trades": [a-1, a-2, b-1, b-2],
    })


def _audit(x=None, y=None, gate=100):
    return audit_signal_capacity({2012: _frame() if x is None else x,
                                  2013: _frame(29, 15) if y is None else y},
                                 min_fills_each_year=gate, rule_columns=("rule",))


def test_fac018_like_signal_upper_bound_rejects_even_before_exit_sweep():
    result = _audit()
    assert result["status"] == "STRUCTURALLY_UNREACHABLE"
    assert [r["max_signals_per_spec"] for r in result["years"]] == [39, 29]
    assert result["correlated_parameter_specs"] == 4


def test_feasible_upper_bound_is_not_an_acceptance_pass():
    result = _audit(_frame(120, 105), _frame(111, 101))
    assert result["status"] == "NOT_DISPROVED_BY_SIGNAL_COUNT"
    assert result["scope"].endswith("NOT_OOS")


def test_one_year_below_gate_is_enough_to_reject():
    assert _audit(_frame(101, 101), _frame(99, 99))["status"] == "STRUCTURALLY_UNREACHABLE"


@pytest.mark.parametrize("change,match", [
    (lambda f: f.assign(signals=[39, 38, 29, 29]), "risk exits changed"),
    (lambda f: f.assign(trades=[40, 37, 28, 27]), "more fills"),
    (lambda f: f.assign(id=["a_0", "a_0", "b_0", "b_1"]), "duplicate"),
    (lambda f: f.assign(signals=[True, True, False, False]), "nonnegative integers"),
    (lambda f: f.assign(signals=[39.0, 39.0, 29.0, 29.0]), "nonnegative integers"),
    (lambda f: f.assign(signals=[-1, -1, 29, 29]), "nonnegative integers"),
    (lambda f: f.drop(columns="rule"), "missing columns"),
    (lambda f: f.assign(rule=["a", None, "b", "b"]), "missing signal-rule"),
])
def test_fail_closed_on_corrupted_counts(change, match):
    with pytest.raises(SignalCapacityError, match=match):
        _audit(change(_frame()))


def test_fail_closed_on_changed_grid():
    with pytest.raises(SignalCapacityError, match="differ by year"):
        _audit(y=_frame().assign(id=["a_0", "a_1", "b_0", "new"]))


@pytest.mark.parametrize("gate", [0, True, 2.5, -1])
def test_reject_invalid_fill_gate(gate):
    with pytest.raises(SignalCapacityError, match="positive integer"):
        _audit(gate=gate)


def test_reject_duplicate_rule_columns():
    with pytest.raises(SignalCapacityError, match="Invalid signal-rule"):
        audit_signal_capacity({2012: _frame(), 2013: _frame()},
                              min_fills_each_year=100, rule_columns=("rule", "rule"))


def test_reject_one_year_only():
    with pytest.raises(SignalCapacityError, match="at least two"):
        audit_signal_capacity({2012: _frame()},
                              min_fills_each_year=100, rule_columns=("rule",))
