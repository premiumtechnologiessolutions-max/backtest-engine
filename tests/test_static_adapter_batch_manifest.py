"""Synthetic-only static adapter batch receipts; no external engines."""
import copy

import pytest

from scripts.static_adapter_envelope import SCHEMA
from scripts.static_external_adapter_registry import REGISTRY
from scripts.static_adapter_batch_manifest import (
    make_static_batch_manifest, validate_static_batch_manifest,
)


def batch():
    name, spec = next(iter(REGISTRY.items()))
    return [
        {"schema": SCHEMA, "adapter": name, "request_id": f"synthetic_{i}",
         "payload_schema": spec.inputs[0],
         "payload": {"field_names": [f"field_{i}"]}}
        for i in (1, 2)
    ]


def test_ordered_batch_is_inert_and_deterministic():
    envelopes = batch()
    before = copy.deepcopy(envelopes)
    manifest = make_static_batch_manifest(envelopes)
    assert validate_static_batch_manifest(envelopes, manifest) == manifest
    assert make_static_batch_manifest(envelopes) == manifest
    assert envelopes == before
    assert manifest["request_count"] == 2
    assert manifest["request_ids"] == ["synthetic_1", "synthetic_2"]
    assert manifest["execution_authorized"] is False
    assert manifest["results_verified"] is False


def test_reordered_envelopes_rejected():
    envelopes = batch()
    manifest = make_static_batch_manifest(envelopes)
    with pytest.raises(ValueError):
        validate_static_batch_manifest(list(reversed(envelopes)), manifest)


def test_reordered_receipts_rejected():
    envelopes = batch()
    manifest = make_static_batch_manifest(envelopes)
    manifest["receipts"].reverse()
    with pytest.raises(ValueError):
        validate_static_batch_manifest(envelopes, manifest)


@pytest.mark.parametrize("field,value", [
    ("manifest_sha256", "0" * 64),
    ("state", "RUNNING"),
    ("request_count", 3),
    ("request_count", True),
    ("adapter_count", 0),
    ("execution_authorized", True),
    ("results_verified", True),
    ("request_ids", ["synthetic_2", "synthetic_1"]),
])
def test_manifest_tampering_rejected(field, value):
    envelopes = batch()
    manifest = make_static_batch_manifest(envelopes)
    manifest[field] = value
    with pytest.raises(ValueError):
        validate_static_batch_manifest(envelopes, manifest)


@pytest.mark.parametrize("mutation", [
    lambda m: m["receipts"].pop(),
    lambda m: m["receipts"][0].update({"execution_authorized": True}),
    lambda m: m["receipts"][0].update({"envelope_sha256": "0" * 64}),
    lambda m: m.update({"extra": "unexpected"}),
])
def test_receipt_omission_or_mutation_rejected(mutation):
    envelopes = batch()
    manifest = make_static_batch_manifest(envelopes)
    mutation(manifest)
    with pytest.raises(ValueError):
        validate_static_batch_manifest(envelopes, manifest)


def test_payload_mutation_breaks_manifest_binding():
    envelopes = batch()
    manifest = make_static_batch_manifest(envelopes)
    envelopes[1]["payload"]["field_names"] = ["changed"]
    with pytest.raises(ValueError):
        validate_static_batch_manifest(envelopes, manifest)


def test_duplicate_request_id_rejected_before_receipt_creation():
    envelopes = batch()
    envelopes[1]["request_id"] = envelopes[0]["request_id"]
    with pytest.raises(ValueError, match="Duplicate"):
        make_static_batch_manifest(envelopes)


@pytest.mark.parametrize("invalid", [[], None, {}, [None]])
def test_invalid_batch_refused(invalid):
    with pytest.raises(ValueError):
        make_static_batch_manifest(invalid)


@pytest.mark.parametrize("invalid", [None, [], {}, {"receipts": []}])
def test_invalid_manifest_refused(invalid):
    with pytest.raises(ValueError):
        validate_static_batch_manifest(batch(), invalid)
