"""Pure construction-only acceptance gate; no market data or execution."""
from __future__ import annotations
import hashlib
import json
import re

CHECKS = (
    "synthetic_unit_tests", "static_security_review", "queue_permissions",
    "resume_idempotence", "registry_provenance", "terminal_accessibility",
    "shared_capacity_simulation", "canonical_adapter_contract",
    "no_live_execution", "private_data_exclusion",
)
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def evaluate(evidence: dict) -> dict:
    """Validate explicit engineering evidence without certifying profitability."""
    if type(evidence) is not dict or set(evidence) != {"source_commit", "checks"}:
        raise ValueError("Invalid evidence envelope")
    commit, checks = evidence["source_commit"], evidence["checks"]
    if type(commit) is not str or not _SHA.fullmatch(commit):
        raise ValueError("Invalid source commit")
    if type(checks) is not dict or set(checks) != set(CHECKS):
        raise ValueError("Missing or unexpected engineering checks")
    passed = []
    for name in CHECKS:
        record = checks[name]
        if type(record) is not dict or set(record) != {"passed", "artifact", "source_commit"}:
            raise ValueError("Invalid evidence record")
        path = record["artifact"]
        if (type(record["passed"]) is not bool or record["source_commit"] != commit
                or type(path) is not str or len(path) > 240
                or not re.fullmatch(r"(?:docs|reports|tests)/[A-Za-z0-9_./-]+", path)
                or any(p in ("", ".", "..") for p in path.split("/"))):
            raise ValueError("Unverifiable engineering evidence")
        if record["passed"]:
            passed.append(name)
    fingerprint = hashlib.sha256(json.dumps(
        evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")).hexdigest()
    return {
        "scope": "ENGINE_CONSTRUCTION_ONLY",
        "source_commit": commit,
        "evidence_fingerprint": fingerprint,
        "passed": len(passed), "total": len(CHECKS),
        "missing": [n for n in CHECKS if n not in passed],
        "engineering_gate_passed": len(passed) == len(CHECKS),
        "real_data_backtests_performed": False,
        "profitability_verified": False,
        "production_approved": False,
    }
