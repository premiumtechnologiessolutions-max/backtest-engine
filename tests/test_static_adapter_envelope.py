"""Synthetic-only checks for inert external adapter envelope validation."""
import copy
import pytest
from scripts.static_adapter_envelope import SCHEMA, validate_static_envelope


def valid():
    return {
        "schema": SCHEMA,
        "adapter": "LEAN",
        "request_id": "synthetic_001",
        "payload_schema": "frozen_request_v1",
        "payload": {"field_names": ["symbol", "timestamp"]},
    }


def test_accepts_inert_schema_without_authorizing_execution():
    summary = validate_static_envelope(valid())
    assert summary["field_count"] == 2
    assert summary["execution_authorized"] is False
    assert summary["results_verified"] is False
    assert "payload" not in summary


@pytest.mark.parametrize("change", [
    {"schema": "OTHER"}, {"adapter": "unknown"},
    {"request_id": "../data"}, {"request_id": ""}, {"request_id": "x" * 97},
    {"payload_schema": "unverified_receipt_v1"},
    {"payload": {"field_names": ["symbol", "symbol"]}},
    {"payload": {"field_names": ["../../secret"]}},
    {"payload": {"field_names": []}},
    {"payload": {"field_names": ["x"] * 33}},
    {"payload": {"field_names": ["symbol"], "command": "execute"}},
    {"payload": {"field_names": ["symbol"], "url": "https://example.test"}},
])
def test_rejects_unsafe_or_ambiguous_envelopes(change):
    item = valid()
    item.update(change)
    with pytest.raises(ValueError):
        validate_static_envelope(item)


def test_rejects_extra_keys_and_wrong_types():
    item = valid()
    item["execute"] = False
    with pytest.raises(ValueError):
        validate_static_envelope(item)
    for bad in (None, [], "json", {"schema": SCHEMA}):
        with pytest.raises(ValueError):
            validate_static_envelope(bad)
    item = valid()
    item["payload"]["field_names"] = ["symbol", 1]
    with pytest.raises(ValueError):
        validate_static_envelope(item)


def test_no_mutation_of_input():
    item = valid()
    before = copy.deepcopy(item)
    validate_static_envelope(item)
    assert item == before
