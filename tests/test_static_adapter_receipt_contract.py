"""Small synthetic-only tests: no engine, worker, data fetch or market fixtures."""
import copy
import pytest
from scripts.static_adapter_envelope import SCHEMA
from scripts.static_external_adapter_registry import REGISTRY
from scripts.static_adapter_receipt_contract import make_static_receipt, validate_static_receipt


def envelope():
    name, spec = next(iter(REGISTRY.items()))
    return {"schema": SCHEMA, "adapter": name, "request_id": "synthetic_1",
            "payload_schema": spec.inputs[0], "payload": {"field_names": ["synthetic_field"]}}


def test_receipt_is_inert_and_bound():
    e = envelope()
    before = copy.deepcopy(e)
    r = make_static_receipt(e)
    assert validate_static_receipt(e, r) == r
    assert e == before
    assert r["execution_authorized"] is False and r["results_verified"] is False


@pytest.mark.parametrize("field,value", [
    ("request_id", "other"), ("envelope_sha256", "0" * 64),
    ("state", "COMPLETE"), ("execution_authorized", True),
    ("results_verified", True), ("results_verified", 0),
])
def test_tampering_fails(field, value):
    e = envelope()
    r = make_static_receipt(e)
    r[field] = value
    with pytest.raises(ValueError):
        validate_static_receipt(e, r)


def test_payload_change_breaks_binding():
    e = envelope()
    r = make_static_receipt(e)
    e["payload"]["field_names"] = ["changed"]
    with pytest.raises(ValueError):
        validate_static_receipt(e, r)


@pytest.mark.parametrize("bad", [None, [], {}, {"extra": 1}])
def test_bad_receipts_fail(bad):
    with pytest.raises(ValueError):
        validate_static_receipt(envelope(), bad)
