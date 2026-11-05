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
