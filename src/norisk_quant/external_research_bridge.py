"""Provider-neutral, offline research interchange with immutable provenance.

This is an original interoperability contract, NOT a vendored implementation of
LEAN, NautilusTrader, OpenBB, RD-Agent, FinRL or TradingAgents. No external
process, network request, trading order, or result approval is performed here.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA = "NRFX_EXTERNAL_RESEARCH_V1"
ENGINE_IDS = frozenset({
    "lean", "nautilus", "openbb", "rd_agent", "tradingagents",
    "finrl", "external_python", "norisk_quant",
})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _sha256(obj: object) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f"Invalid SHA256: {label}")
    return value


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError(f"Invalid name: {label}")
    return value


def request(engine: str, *, source_sha256: str, code_sha256: str,
            spec_sha256: str, dataset: str, experiment_id: str) -> dict:
    """Describe an offline research request; all source identities are required.

    A provider adapter may translate this envelope to its native format.
    This function intentionally refuses credentials, executable commands,
    broker accounts, shell arguments, and optional arbitrary metadata.
    """
    if engine not in ENGINE_IDS:
        raise ValueError("Provider is not allowlisted")
    _name(dataset, "dataset")
    _name(experiment_id, "experiment_id")
    result = {
        "schema": SCHEMA, "kind": "research_request", "engine": engine,
        "scope": "offline_research_only", "dataset": dataset,
        "experiment_id": experiment_id,
        "source_sha256": _hash(source_sha256, "source"),
        "code_sha256": _hash(code_sha256, "code"),
        "spec_sha256": _hash(spec_sha256, "spec"),
    }
    result["request_sha256"] = _sha256(result)
    return result


def verify_request(envelope: Mapping[str, Any]) -> dict:
    if not isinstance(envelope, dict):
        raise ValueError("Expected plain JSON request object")
    fields = {"schema", "kind", "engine", "scope", "dataset",
              "experiment_id", "source_sha256", "code_sha256",
              "spec_sha256", "request_sha256"}
    if set(envelope) != fields or envelope.get("scope") != "offline_research_only":
        raise ValueError("Unexpected or unsafe request fields")
    rebuilt = request(
        envelope["engine"], source_sha256=envelope["source_sha256"],
        code_sha256=envelope["code_sha256"],
        spec_sha256=envelope["spec_sha256"], dataset=envelope["dataset"],
        experiment_id=envelope["experiment_id"],
    )
    if envelope != rebuilt:
        raise ValueError("Request fingerprint mismatch")
    return rebuilt


def result_receipt(envelope: Mapping[str, Any], *, provider_build_sha256: str,
                   artifact_sha256: str, status: str) -> dict:
    """Wrap externally produced evidence; never certify results as ACCEPTED."""
    verified = verify_request(envelope)
    if status not in {"completed_unverified", "failed"}:
        raise ValueError("External results cannot self-certify acceptance")
    receipt = {
        "schema": SCHEMA, "kind": "external_result_receipt",
        "request_sha256": verified["request_sha256"],
        "engine": verified["engine"],
        "provider_build_sha256": _hash(provider_build_sha256, "provider_build"),
        "artifact_sha256": _hash(artifact_sha256, "artifact"),
        "status": status, "accepted": False,
    }
    receipt["receipt_sha256"] = _sha256(receipt)
    return receipt


def verify_result(envelope: Mapping[str, Any], receipt: Mapping[str, Any],
                  *, actual_artifact_sha256: str) -> dict:
    """Check receipt binding and bytes digest; independent audit remains required."""
    req = verify_request(envelope)
    if not isinstance(receipt, dict):
        raise ValueError("Expected plain JSON result object")
    fields = {"schema", "kind", "request_sha256", "engine",
              "provider_build_sha256", "artifact_sha256", "status",
              "accepted", "receipt_sha256"}
    if set(receipt) != fields or receipt.get("accepted") is not False:
        raise ValueError("External receipt cannot claim acceptance")
    if (receipt.get("request_sha256") != req["request_sha256"]
            or receipt.get("engine") != req["engine"]
            or receipt.get("artifact_sha256") != actual_artifact_sha256):
        raise ValueError("External receipt not bound to request and artifact")
    rebuilt = result_receipt(
        req, provider_build_sha256=receipt["provider_build_sha256"],
        artifact_sha256=_hash(actual_artifact_sha256, "actual_artifact"),
        status=receipt["status"],
    )
    if receipt != rebuilt:
        raise ValueError("External receipt fingerprint mismatch")
    return rebuilt
