"""Synthetic regression cases for signal-only joint-ID feasibility."""
import pandas as pd
import pytest
from scripts.preflight_signal_capacity import PreflightError, preflight_signal_capacity


def frame(a=110, b=95):
    return pd.DataFrame({
        "id": ["a_1", "a_2", "b_1", "b_2"],
        "rule": ["a", "a", "b", "b"],
        "stop": [1, 2, 1, 2],
        "signals": [a, a, b, b],
    })


def audit(x=None, y=None, gate=100):
    return preflight_signal_capacity(
        {2012: frame() if x is None else x,
         2013: frame(95, 110) if y is None else y},
        min_fills_each_year=gate, rule_columns=("rule",),
    )


def test_disjoint_yearly_maxima_do_not_prove_any_same_id_qualifies():
    r = audit()
    assert [y["max_signals_per_spec"] for y in r["years"]] == [110, 110]
    assert [y["specs_meeting_necessary_signal_count"] for y in r["years"]] == [2, 2]
    assert r["same_specs_meeting_signal_gate_in_all_years"] == 0
    assert r["status"] == "STRUCTURALLY_UNREACHABLE"


def test_joint_signal_sufficiency_does_not_mean_acceptance():
    r = audit(frame(120, 110), frame(110, 120))
    assert r["same_specs_meeting_signal_gate_in_all_years"] == 4
    assert r["status"] == "NOT_DISPROVED_BY_SIGNAL_COUNT"
    assert r["scope"].endswith("NOT_OOS")


def test_one_year_below_threshold_is_impossible():
    assert audit(frame(110, 101), frame(99, 99))["status"] == "STRUCTURALLY_UNREACHABLE"


def test_trades_not_needed_before_execution():
    assert "trades" not in frame()
    assert audit()["correlated_parameter_specs"] == 4


def test_row_order_does_not_change_result():
    assert audit(frame().iloc[::-1].reset_index(drop=True),
                 frame(95, 110).iloc[::-1].reset_index(drop=True)) == audit()


@pytest.mark.parametrize("mutate,reason", [
    (lambda f: f.assign(signals=[110, 109, 95, 95]), "risk-exit"),
    (lambda f: f.assign(signals=[110., 110., 95., 95.]), "native nonnegative"),
    (lambda f: f.assign(signals=[True, True, False, False]), "native nonnegative"),
    (lambda f: f.assign(signals=[-1, -1, 95, 95]), "native nonnegative"),
    (lambda f: f.assign(id=["a_1", "a_1", "b_1", "b_2"]), "duplicate"),
    (lambda f: f.assign(id=["", "a_2", "b_1", "b_2"]), "invalid"),
    (lambda f: f.drop(columns="signals"), "missing columns"),
    (lambda f: f.assign(rule=["a", None, "b", "b"]), "missing signal-rule"),
    (lambda f: f.assign(rule=["a", "a", "", ""]), "invalid signal-rule"),
])
def test_bad_evidence_fails_closed(mutate, reason):
    with pytest.raises(PreflightError, match=reason):
        audit(x=mutate(frame()))


def test_frozen_ids_must_match():
    with pytest.raises(PreflightError, match="IDs differ"):
        audit(y=frame(95, 110).assign(id=["new", "a_2", "b_1", "b_2"]))


def test_frozen_rule_mapping_must_match():
    with pytest.raises(PreflightError, match="mapping changed"):
        audit(y=frame(95, 110).assign(rule=["b", "b", "a", "a"]))


@pytest.mark.parametrize("gate", [0, True, 1.5, -1])
def test_invalid_gate_rejected(gate):
    with pytest.raises(PreflightError, match="positive native integer"):
        audit(gate=gate)


def test_at_least_two_years_required():
    with pytest.raises(PreflightError, match="at least two"):
        preflight_signal_capacity({2012: frame()}, min_fills_each_year=100,
                                  rule_columns=("rule",))


def test_duplicate_grouping_columns_rejected():
    with pytest.raises(PreflightError, match="Invalid signal-rule"):
        preflight_signal_capacity({2012: frame(), 2013: frame()},
                                  min_fills_each_year=100,
                                  rule_columns=("rule", "rule"))


def test_boolean_year_rejected():
    with pytest.raises(PreflightError, match="integer calendar years"):
        preflight_signal_capacity({True: frame(), 2013: frame()},
                                  min_fills_each_year=100,
                                  rule_columns=("rule",))
