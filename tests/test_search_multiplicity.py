"""Synthetic exact joint sign-flip maxT diagnostic; never a live edge claim."""
import copy
import pytest
from norisk_quant.search_multiplicity import exact_joint_signflip

A = "a" * 64
B = "b" * 64
C = "c" * 64


def test_exact_oppositely_correlated_3year_max_statistic():
    d = exact_joint_signflip({A: [1., 1., 1.], B: [-1., -1., -1.]})
    assert d["enumerated_joint_patterns"] == 8
    assert d["independent_oos_proven"] is False
    assert d["selection_or_live_authority"] == "NONE"
    assert d["results"][A]["one_sided_unadjusted_exact_fraction"] == [1, 8]
    assert d["results"][A]["maxT_family_adjusted_exact_fraction"] == [2, 8]
    assert d["results"][B]["one_sided_unadjusted_exact_fraction"] == [8, 8]
    assert d["results"][B]["maxT_family_adjusted_exact_fraction"] == [8, 8]


def test_perfectly_correlated_duplicates_do_not_automatically_double_penalty():
    d = exact_joint_signflip({A: [1., 1., 1.], B: [1., 1., 1.]})
    assert d["results"][A]["maxT_family_adjusted_exact_fraction"] == [1, 8]
    assert d["results"][B]["maxT_family_adjusted_exact_fraction"] == [1, 8]


def test_zero_signal_has_uninformative_probability_one():
    d = exact_joint_signflip({A: [0., 0., 0.], B: [2., 0., 0.]})
    assert d["results"][A]["one_sided_unadjusted_p"] == 1
    assert d["results"][A]["maxT_family_adjusted_p"] == 1


def test_candidate_insertion_order_and_chunk_size_do_not_affect_exact_fractions():
    matrix = {B: [4., -3., 2., 1., 2.], A: [1., 2., -4., 2., 3.],
              C: [-5., 2., 2., 3., 1.]}
    original = exact_joint_signflip(matrix, chunk_size=256)
    changed = exact_joint_signflip(dict(reversed(list(matrix.items()))), chunk_size=2)
    assert original == changed


def test_many_candidates_one_joint_family_not_separate_fake_pvalue_families():
    matrix = {format(i, "064x"): [float((i + year) % 5 - 2)
             for year in range(7)] for i in range(1, 30)}
    d = exact_joint_signflip(matrix)
    assert d["candidate_count"] == 29
    assert d["training_year_blocks"] == 7
    assert d["enumerated_joint_patterns"] == 128
    for p in d["results"].values():
        assert p["maxT_family_adjusted_p"] >= p["one_sided_unadjusted_p"]


@pytest.mark.parametrize("annual", [
    {},
    {A: []},
    {A: [1.]},
    {A: [1., 2.], B: [1., 2., 3.]},
    {A: [True, 2.]},
    {A: [float("nan"), 2.]},
    {A: [float("inf"), 2.]},
    {A: ["1", 2.]},
    {A: (1., 2.)},
    {"unsafe": [1., 2.]},
    {A: [1.] * 17},
])
def test_unfrozen_or_invalid_annual_return_matrix_fails_closed(annual):
    with pytest.raises(ValueError):
        exact_joint_signflip(annual)


@pytest.mark.parametrize("opts", [
    {"chunk_size": 0}, {"chunk_size": True},
    {"min_years": 1}, {"max_years": 1},
    {"max_years": True}, {"chunk_size": 4097},
])
def test_reject_invalid_test_budget_parameters(opts):
    with pytest.raises(ValueError):
        exact_joint_signflip({A: [1., 2.]}, **opts)
