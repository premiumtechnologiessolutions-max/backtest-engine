"""Read-only continuity comparison across two audited durable design stores.

No execution, job submission, database writes, or research certification.
The two snapshots are acquired independently; this is not an atomic
cross-database transaction or a provenance attestation.
"""
from __future__ import annotations

import os
import stat

from scripts.durable_research_state import DurableResearchState
from scripts.static_design_inventory import snapshot_static_design_records
from scripts.static_design_continuity import verify_static_design_continuity


def compare_audited_static_design_stores(
    previous: DurableResearchState, current: DurableResearchState
) -> dict:
    """Fail closed if either database cannot produce an audited snapshot."""
    if not isinstance(previous, DurableResearchState) or not isinstance(current, DurableResearchState):
        raise ValueError("Expected two durable state stores")
    # Pin both physical file identities before reading. Recheck after both
    # snapshots: path replacement during an audit invalidates its evidence.
    try:
        before_ids = tuple(os.stat(store.database) for store in (previous, current))
        if not all(stat.S_ISREG(item.st_mode) for item in before_ids):
            raise ValueError("SQLite store must be a regular file")
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("Cannot verify both SQLite store paths") from exc
    if (before_ids[0].st_dev, before_ids[0].st_ino) == (before_ids[1].st_dev, before_ids[1].st_ino):
        raise ValueError("Baseline and current must be distinct SQLite stores")
    # Do not silently treat an unreadable previous store as an empty baseline.
    before = snapshot_static_design_records(previous)
    after = snapshot_static_design_records(current)
    try:
        after_ids = tuple(os.stat(store.database) for store in (previous, current))
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("SQLite store path changed during comparison") from exc
    if any((a.st_dev, a.st_ino) != (b.st_dev, b.st_ino) for a, b in zip(before_ids, after_ids)):
        raise ValueError("SQLite store path changed during comparison")
    result = verify_static_design_continuity(before, after)
    return {**result, "snapshots_audited": True, "provenance_verified": False}
