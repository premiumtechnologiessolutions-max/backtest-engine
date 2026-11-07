"""Inert adapter receipt preflight. No market IO, execution or verification."""
from __future__ import annotations

import hashlib
import json
from scripts.static_adapter_envelope import validate_static_envelope

RECEIPT_SCHEMA = "NRFX_STATIC_ADAPTER_RECEIPT_V1"
_KEYS = frozenset({"schema", "request_id", "adapter", "envelope_sha256", "state", "execution_authorized", "results_verified"})


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def make_static_receipt(envelope: object) -> dict:
    summary = validate_static_envelope(envelope)
    return {"schema": RECEIPT_SCHEMA, "request_id": summary["request_id"],
            "adapter": summary["adapter"], "envelope_sha256": _digest(envelope),
            "state": "DESIGN_ONLY_DISABLED", "execution_authorized": False,
            "results_verified": False}


def validate_static_receipt(envelope: object, receipt: object) -> dict:
    """Check exact receipt binding; never endorse results or enable execution."""
    expected = make_static_receipt(envelope)
    if type(receipt) is not dict or set(receipt) != _KEYS:
        raise ValueError("Invalid static receipt structure")
    if any(type(receipt[k]) is not type(expected[k]) or receipt[k] != expected[k] for k in _KEYS):
        raise ValueError("Receipt does not match inert request")
    return dict(expected)
