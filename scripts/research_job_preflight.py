"""Read-only checkout/source preflight for queued research metadata.

Never starts a backtest, imports private quote data, or marks work completed.
This gate must be passed again immediately before any future authorized worker.
"""
from __future__ import annotations

import argparse
import hmac
import json
from pathlib import Path
import re
import subprocess

try:
    from scripts.research_job_queue import (
        COMMIT, ROOT, _read_source, _registry_hash, list_jobs,
    )
except ModuleNotFoundError:  # direct invocation from repository root
    from research_job_queue import (
        COMMIT, ROOT, _read_source, _registry_hash, list_jobs,
    )

FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")


def _git_head(root: Path) -> str:
    """Read the actual checkout HEAD, not a caller's asserted commit."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=root,
            capture_output=True, text=True, check=True, timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Cannot verify local Git checkout HEAD") from exc
    sha = result.stdout.strip()
    if not COMMIT.fullmatch(sha):
        raise ValueError("Invalid local Git checkout HEAD")
    # HEAD alone does not bind local edits. Check tracked files throughout
    # the checkout, then reject untracked source/scripts that could shadow
    # imported code even though they do not change the frozen Git SHA.
    # This remains metadata-only; a future worker needs a sandboxed build.
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Cannot verify tracked checkout cleanliness") from exc
    if dirty.strip():
        raise ValueError("Tracked checkout differs from frozen Git revision")
    try:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", "src", "scripts"],
            cwd=root, capture_output=True, text=True, check=True, timeout=5,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Cannot verify untracked source cleanliness") from exc
    if untracked.strip():
        raise ValueError("Untracked source files invalidate frozen Git revision")
    return sha


def preflight_job(root: Path, fingerprint: str) -> dict:
    """Fail closed on stale frozen metadata and wrong checkout; no execution.

    The queue record remains QUEUED_NOT_EXECUTED even after this check.
    No data availability, CI, OOS or result attestation is implied.
    """
    if type(fingerprint) is not str or not FINGERPRINT.fullmatch(fingerprint):
        raise ValueError("Invalid queue fingerprint")
    # list_jobs verifies permissions, strict schema and every queue fingerprint.
    matches = [job for job in list_jobs(root) if job["fingerprint"] == fingerprint]
    if len(matches) != 1:
        raise ValueError("Queued fingerprint not found exactly once")
    job = matches[0]
    current_spec = _read_source(root, job["frozen_spec"])
    current_registry = _registry_hash(root)
    if not hmac.compare_digest(current_spec, job["frozen_spec_sha256"]):
        raise ValueError("Frozen specification changed since enqueue")
    if not hmac.compare_digest(current_registry, job["registry_sha256"]):
        raise ValueError("Research registry changed since enqueue")
    head = _git_head(root)
    if not hmac.compare_digest(head, job["source_commit"]):
        raise ValueError("Git checkout HEAD differs from frozen request")
    return {
        "fingerprint": fingerprint,
        "family": job["family"],
        "source_commit": head,
        "frozen_spec_sha256": current_spec,
        "registry_sha256": current_registry,
        "status": "MATCHED_METADATA_ONLY_NOT_EXECUTED",
        "backtests_executed": 0,
        "monthly_pnl_observations": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fingerprint", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(preflight_job(ROOT, args.fingerprint), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
