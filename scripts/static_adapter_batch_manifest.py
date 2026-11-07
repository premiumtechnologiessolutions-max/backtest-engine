"""Inert batch receipt manifest with complete ordered binding.

Pure-data engineering contract only: no filesystem, network, market access,
engine imports, scheduling, or acceptance authority.
"""
from __future__ import annotations

import hashlib
import json

from scripts.static_adapter_batch import validate_static_batch
from scripts.static_adapter_receipt_contract import (
    make_static_receipt, validate_static_receipt,
)

SCHEMA = "NRFX_STATIC_ADAPTER_BATCH_RECEIPT_V1"
_KEYS = frozenset({
    "schema", "state", "request_count", "adapter_count",
    "request_ids", "receipts", "manifest_sha256",
    "execution_authorized", "results_verified",
})


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def make_static_batch_manifest(envelopes: object) -> dict:
    """Bind each request in original order, without starting anything."""
    summary = validate_static_batch(envelopes)
    receipts = [make_static_receipt(envelope) for envelope in envelopes]
    payload = {
        "schema": SCHEMA,
        "state": "DESIGN_ONLY_DISABLED",
        "request_count": summary["request_count"],
        "adapter_count": summary["adapter_count"],
        "request_ids": [receipt["request_id"] for receipt in receipts],
        "receipts": receipts,
        "execution_authorized": False,
        "results_verified": False,
    }
    return {**payload, "manifest_sha256": _hash(payload)}


def validate_static_batch_manifest(envelopes: object, manifest: object) -> dict:
    """Reject missing, extra, reordered, mutated, or privileged receipts."""
    expected = make_static_batch_manifest(envelopes)
    if type(manifest) is not dict or set(manifest) != _KEYS:
        raise ValueError("Invalid static batch manifest schema")
    if type(manifest["receipts"]) is not list or (
        len(manifest["receipts"]) != expected["request_count"]
    ):
        raise ValueError("Static batch receipt count mismatch")
    for envelope, receipt in zip(envelopes, manifest["receipts"]):
        validate_static_receipt(envelope, receipt)
    # Strict equality also rejects booleans disguised as integer counters.
    for key in _KEYS:
        if type(manifest[key]) is not type(expected[key]) or manifest[key] != expected[key]:
            raise ValueError("Static batch manifest identity or permission drift")
    return expected
