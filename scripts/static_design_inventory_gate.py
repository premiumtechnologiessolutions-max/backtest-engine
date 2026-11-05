"""Pure, non-executable comparison gate for audited static-design inventories."""
from __future__ import annotations

import re

SCHEMA = "NRFX_STATIC_DESIGN_INVENTORY_V1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_KEYS = frozenset({"schema", "design_schema", "batches", "requests",
                   "inventory_sha256", "execution_authorized",
                   "results_verified", "jobs_created"})


def _check(snapshot: object) -> dict:
    if type(snapshot) is not dict or set(snapshot) != _KEYS:
        raise ValueError("Invalid inventory snapshot fields")
    if snapshot["schema"] != SCHEMA or snapshot["design_schema"] != "NRFX_DURABLE_STATIC_ADAPTER_DESIGNS_V1":
        raise ValueError("Invalid inventory schema")
    for key in ("batches", "requests", "jobs_created"):
        if type(snapshot[key]) is not int or snapshot[key] < 0:
            raise ValueError("Invalid inventory counter")
    if snapshot["requests"] < snapshot["batches"]:
        raise ValueError("Inconsistent inventory counters")
    if snapshot["jobs_created"] != 0 or snapshot["execution_authorized"] is not False or snapshot["results_verified"] is not False:
        raise ValueError("Privileged inventory snapshot")
    if type(snapshot["inventory_sha256"]) is not str or not _DIGEST.fullmatch(snapshot["inventory_sha256"]):
        raise ValueError("Invalid inventory fingerprint")
    return snapshot


def compare_static_design_inventories(previous: object, current: object) -> dict:
    """Compare already-audited snapshots; never touch storage or jobs.

    Snapshot hashes are not authenticated signatures or authorization tokens.
    """
    old = _check(previous)
    new = _check(current)
    changed = old["inventory_sha256"] != new["inventory_sha256"]
    if not changed and (old["batches"], old["requests"]) != (new["batches"], new["requests"]):
        raise ValueError("Matching inventory fingerprint with conflicting counters")
    removal_detected = new["batches"] < old["batches"] or new["requests"] < old["requests"]
    return {
        "schema": "NRFX_STATIC_DESIGN_INVENTORY_COMPARISON_V1",
        "changed": changed,
        "removal_detected": removal_detected,
        "batch_delta": new["batches"] - old["batches"],
        "request_delta": new["requests"] - old["requests"],
        "status": ("REMOVAL_REVIEW_REQUIRED" if removal_detected else
                   "CHANGED_REVIEW_REQUIRED" if changed else "UNCHANGED"),
        "execution_authorized": False,
        "results_verified": False,
        "jobs_created": 0,
    }
