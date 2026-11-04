"""Bind external research envelopes to existing immutable queue claims.

This adapter checks provenance identity only. It neither runs external engines
nor certifies result correctness. Original dataset bytes and provider build
must be independently attested before any execution or acceptance.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from norisk_quant.external_research_bridge import (
    request, result_receipt, verify_request, verify_result,
)
from scripts.research_job_queue import _verify

SCHEMA = "NRFX_QUEUE_EXTERNAL_BINDING_V1"


def _fingerprint(record: dict) -> str:
    if type(record) is not dict:
        raise ValueError("Frozen queue record must be a plain object")
    ident = record.get("fingerprint")
    if type(ident) is not str:
        raise ValueError("Frozen queue fingerprint missing")
    _verify(record, ident + ".json")
    return ident


def _experiment_id(ident: str) -> str:
    return "exp_" + ident[:32]


def _claim(record: dict, claim: dict) -> None:
    ident = _fingerprint(record)
    if type(claim) is not dict or claim.get("request_id") != ident:
        raise ValueError("Claim not bound to frozen queue record")
    if type(claim.get("frozen_request")) is not dict or claim["frozen_request"] != record:
        raise ValueError("Claim frozen request differs")
    if (type(claim.get("attempt_no")) is not int or claim["attempt_no"] < 1
            or type(claim.get("fencing_token")) is not int
            or claim["fencing_token"] < 1
            or type(claim.get("attempt_id")) is not str
            or len(claim["attempt_id"]) != 32
            or not all(c in "0123456789abcdef" for c in claim["attempt_id"])):
        raise ValueError("Invalid durable attempt identity")
    if type(claim.get("worker")) is not str or not claim["worker"]:
        raise ValueError("Missing worker identity")


def bind_claim(record: dict, claim: dict, *, engine: str,
               source_sha256: str, code_sha256: str,
               dataset: str = "xauusd_m1") -> dict:
    """Create a tamper-evident binding across queue, lease and provider.

    Callers must separately confirm code_sha256 against source_commit,
    source_sha256 against the private data and the lease's current ownership.
    """
    _claim(record, claim)
    envelope = request(engine, source_sha256=source_sha256,
                       code_sha256=code_sha256,
                       spec_sha256=record["frozen_spec_sha256"],
                       dataset=dataset, experiment_id=_experiment_id(record["fingerprint"]))
    binding = {
        "schema": SCHEMA,
        "frozen_queue_fingerprint": record["fingerprint"],
        "source_commit": record["source_commit"],
        "attempt_id": claim["attempt_id"],
        "attempt_no": claim["attempt_no"],
        "fencing_token": claim["fencing_token"],
        "worker": claim["worker"],
        "external_request": envelope,
        "execution_authorized": False,
        "result_accepted": False,
    }
    binding["binding_sha256"] = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True, allow_nan=False).encode("ascii")
    ).hexdigest()
    return binding


def verify_binding(record: dict, claim: dict, binding: dict) -> dict:
    """Validate a frozen binding without inferring a currently valid lease."""
    _claim(record, claim)
    if type(binding) is not dict:
        raise ValueError("Invalid external binding")
    envelope = binding.get("external_request")
    verified = verify_request(envelope)
    rebuilt = bind_claim(
        record, claim, engine=verified["engine"],
        source_sha256=verified["source_sha256"],
        code_sha256=verified["code_sha256"], dataset=verified["dataset"],
    )
    if binding != rebuilt:
        raise ValueError("External binding mismatch")
    return rebuilt


def bind_unverified_receipt(record: dict, claim: dict, binding: dict,
                            receipt: dict, *, actual_artifact_sha256: str) -> dict:
    """Attach an unverified provider receipt to a frozen lease-bound request.

    This deliberately does not change DurableResearchState or set ACCEPTED.
    """
    verified = verify_binding(record, claim, binding)
    result = verify_result(verified["external_request"], receipt,
                           actual_artifact_sha256=actual_artifact_sha256)
    return {
        "schema": SCHEMA, "binding_sha256": verified["binding_sha256"],
        "receipt_sha256": result["receipt_sha256"],
        "status": result["status"], "accepted": False,
    }
