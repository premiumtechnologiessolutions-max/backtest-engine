"""Synthetic-only batch preflight contract tests."""
import copy
import pytest
from scripts.static_adapter_batch import validate_static_batch
from scripts.static_adapter_envelope import SCHEMA


def envelope(request_id="synthetic_001"):
    return {"schema": SCHEMA, "adapter": "LEAN", "request_id": request_id,
            "payload_schema": "frozen_request_v1",
            "payload": {"field_names": ["symbol"]}}


def test_valid_inert_batch_and_no_mutation():
    batch = [envelope("synthetic_001"), envelope("synthetic_002")]
    before = copy.deepcopy(batch)
    result = validate_static_batch(batch)
    assert result == {"status": "DESIGN_ONLY_DISABLED", "request_count": 2,
                      "adapter_count": 1, "execution_authorized": False,
                      "results_verified": False}
    assert batch == before


@pytest.mark.parametrize("batch", [None, {}, (), [], [envelope()] * 33,
                                        [envelope(), envelope()],
                                        [envelope(), {**envelope("synthetic_002"), "execute": True}]])
def test_rejects_invalid_batch_atomically(batch):
    with pytest.raises(ValueError):
        validate_static_batch(batch)
