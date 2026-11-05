"""Synthetic-safe, read-only continuity proof for static design records.

Inventory digests and counts alone cannot establish that old records survived.
This module compares immutable (batch ID, request ID, payload digest) tuples.
It never reads a database, starts a worker, or authorizes execution.
"""
from __future__ import annotations

import re

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_MAX_RECORDS = 10000


def _records(value: object) -> dict[tuple[str, str], str]:
    if type(value) is not list or len(value) > _MAX_RECORDS:
        raise ValueError("Invalid record manifest")
    records: dict[tuple[str, str], str] = {}
    for row in value:
        if type(row) is not dict or set(row) != {"batch_id", "request_id", "payload_sha256"}:
            raise ValueError("Invalid manifest row")
        batch, request, digest = (row[k] for k in ("batch_id", "request_id", "payload_sha256"))
        if (type(batch) is not str or not 1 <= len(batch) <= 128 or
                type(request) is not str or not 1 <= len(request) <= 128 or
                type(digest) is not str or not _HEX.fullmatch(digest)):
            raise ValueError("Invalid manifest identity or digest")
        key = (batch, request)
        if key in records:
            raise ValueError("Duplicate manifest identity")
        records[key] = digest
    return records


def verify_static_design_continuity(previous: object, current: object) -> dict:
    """Report record-level continuity; never certify research or execution.

    Manifests must come from independently audited snapshots. This function
    establishes only consistency of supplied manifests, not their provenance.
    """
    old, new = _records(previous), _records(current)
    removed = sorted(set(old) - set(new))
    modified = sorted(key for key in old.keys() & new.keys() if old[key] != new[key])
    added = sorted(set(new) - set(old))
    return {
        "schema": "NRFX_STATIC_DESIGN_CONTINUITY_V1",
        "continuity_preserved": not removed and not modified,
        "review_required": bool(removed or modified or added),
        "removed": len(removed),
        "modified": len(modified),
        "added": len(added),
        "execution_authorized": False,
        "results_verified": False,
        "jobs_created": 0,
    }
