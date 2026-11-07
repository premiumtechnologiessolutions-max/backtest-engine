"""Synthetic-only tests for the pure inventory comparison gate."""
import copy
import pytest
from scripts.static_design_inventory_gate import compare_static_design_inventories


def snapshot(**overrides):
    data = dict(schema="NRFX_STATIC_DESIGN_INVENTORY_V1",
                design_schema="NRFX_DURABLE_STATIC_ADAPTER_DESIGNS_V1",
                batches=1, requests=2, inventory_sha256="a" * 64,
                execution_authorized=False, results_verified=False, jobs_created=0)
    data.update(overrides)
    return data


def test_identical_is_inert():
    before = snapshot()
    original = copy.deepcopy(before)
    result = compare_static_design_inventories(before, before)
    assert result["status"] == "UNCHANGED"
    assert result["changed"] is False
    assert result["jobs_created"] == 0
    assert before == original


def test_changed_fingerprint_requires_review():
    result = compare_static_design_inventories(snapshot(), snapshot(inventory_sha256="b" * 64, batches=2, requests=3))
    assert result["status"] == "CHANGED_REVIEW_REQUIRED"
    assert result["batch_delta"] == result["request_delta"] == 1
    assert result["execution_authorized"] is False


@pytest.mark.parametrize("changes", [
    {"execution_authorized": True}, {"results_verified": True},
    {"jobs_created": 1}, {"jobs_created": False},
    {"batches": True}, {"requests": -1}, {"batches": 3},
    {"inventory_sha256": "A" * 64}, {"inventory_sha256": "abc"},
    {"schema": "unknown"}, {"design_schema": "unknown"},
    {"unexpected": "x"},
])
def test_invalid_or_privileged_snapshots_rejected(changes):
    with pytest.raises(ValueError):
        compare_static_design_inventories(snapshot(), snapshot(**changes))


def test_non_dict_and_missing_fields_rejected():
    with pytest.raises(ValueError):
        compare_static_design_inventories(None, snapshot())
    broken = snapshot()
    del broken["requests"]
    with pytest.raises(ValueError):
        compare_static_design_inventories(snapshot(), broken)


@pytest.mark.parametrize("counter_changes", [
    {"batches": 2, "requests": 2},
    {"requests": 3},
    {"batches": 2, "requests": 4},
])
def test_same_digest_cannot_disagree_on_counts(counter_changes):
    with pytest.raises(ValueError, match="conflicting counters"):
        compare_static_design_inventories(snapshot(), snapshot(**counter_changes))


def test_changed_digest_with_same_counts_still_requires_review():
    result = compare_static_design_inventories(snapshot(), snapshot(inventory_sha256="b" * 64))
    assert result["status"] == "CHANGED_REVIEW_REQUIRED"
    assert result["batch_delta"] == result["request_delta"] == 0
    assert result["execution_authorized"] is False


@pytest.mark.parametrize("previous,current,expected", [
    (snapshot(batches=3, requests=7), snapshot(batches=2, requests=7, inventory_sha256="b" * 64), (-1, 0)),
    (snapshot(batches=2, requests=7), snapshot(batches=2, requests=6, inventory_sha256="b" * 64), (0, -1)),
    (snapshot(batches=3, requests=7), snapshot(batches=1, requests=2, inventory_sha256="b" * 64), (-2, -5)),
])
def test_inventory_shrinkage_requires_distinct_review(previous, current, expected):
    result = compare_static_design_inventories(previous, current)
    assert result["status"] == "REMOVAL_REVIEW_REQUIRED"
    assert result["removal_detected"] is True
    assert (result["batch_delta"], result["request_delta"]) == expected
    assert result["execution_authorized"] is False
    assert result["results_verified"] is False
    assert result["jobs_created"] == 0


def test_nonshrinking_change_is_not_removal():
    result = compare_static_design_inventories(snapshot(), snapshot(inventory_sha256="b" * 64))
    assert result["status"] == "CHANGED_REVIEW_REQUIRED"
    assert result["removal_detected"] is False


def test_identical_inventory_has_no_removal():
    result = compare_static_design_inventories(snapshot(), snapshot())
    assert result["status"] == "UNCHANGED"
    assert result["removal_detected"] is False


@pytest.mark.parametrize("old,new,review,continuity", [
    (snapshot(), snapshot(), False, False),
    (snapshot(), snapshot(inventory_sha256="b" * 64), True, True),
    (snapshot(), snapshot(inventory_sha256="b" * 64, batches=2, requests=3), True, True),
    (snapshot(batches=2, requests=3), snapshot(inventory_sha256="b" * 64), True, True),
])
def test_comparison_never_infers_append_only_continuity(old, new, review, continuity):
    result = compare_static_design_inventories(old, new)
    assert result["review_required"] is review
    assert result["continuity_unverified"] is continuity
    assert result["execution_authorized"] is False
    assert result["results_verified"] is False
    assert result["jobs_created"] == 0
