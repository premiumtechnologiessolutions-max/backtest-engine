"""Pure, fail-closed identity primitive for proposed durable research jobs.

Not a scheduler, persistence layer, or accepted research receipt.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

_FIELDS = (
    "schema_version", "experiment_id", "strategy_ast_sha256",
    "data_source_sha256", "bid_ask_fingerprint", "git_commit_sha",
    "dependency_lock_sha256", "execution_policy_sha256",
    "cost_policy_sha256", "period_start_utc", "period_end_utc",
    "random_seed",
)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HASH_FIELDS = {
    "strategy_ast_sha256", "data_source_sha256", "bid_ask_fingerprint",
    "dependency_lock_sha256", "execution_policy_sha256", "cost_policy_sha256",
}


def canonical_job_identity(manifest: Mapping[str, object]) -> tuple[str, bytes]:
    """Return (sha256 hex job_id, canonical UTF-8 bytes), without mutating inputs.

    Refuses unknown keys, floats, booleans, paths, non-UTC timestamps, and
    incomplete provenance rather than silently coercing identity inputs.
    """
    if not isinstance(manifest, Mapping) or set(manifest) != set(_FIELDS):
        raise ValueError("job identity requires exactly the frozen manifest fields")
    for key in _FIELDS:
        value = manifest[key]
        if key == "random_seed":
            if type(value) is not int or not (0 <= value < 2**63):
                raise ValueError("random_seed must be a nonnegative signed 63-bit integer")
            continue
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(f"{key} must be a nonempty canonical string")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError(f"{key} contains control characters")
        if key in _HASH_FIELDS and not _HEX64.fullmatch(value):
            raise ValueError(f"{key} must be lowercase sha256 hex")
        if key == "git_commit_sha" and not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("git_commit_sha must be a full lowercase SHA1")
        if key in ("period_start_utc", "period_end_utc"):
            from datetime import datetime, timezone
            try:
                parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError as exc:
                raise ValueError(f"{key} must use UTC seconds with Z") from exc
            if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
                raise ValueError(f"{key} must be canonical UTC")
    if manifest["period_start_utc"] >= manifest["period_end_utc"]:
        raise ValueError("period must have positive duration")
    payload = json.dumps(
        dict(manifest), sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), payload
