"""Read-only continuity comparison across two audited durable design stores.

No execution, job submission, database writes, or research certification.
The two snapshots are acquired independently; this is not an atomic
cross-database transaction or a provenance attestation.
"""
from __future__ import annotations

import os

from scripts.durable_research_state import DurableResearchState
from scripts.static_design_inventory import snapshot_static_design_records
from scripts.static_design_continuity import verify_static_design_continuity


def compare_audited_static_design_stores(
    previous: DurableResearchState, current: DurableResearchState
) -> dict:
    """Fail closed if either database cannot produce an audited snapshot."""
    if not isinstance(previous, DurableResearchState) or not isinstance(current, DurableResearchState):
        raise ValueError("Expected two durable state stores")
    # Same-file and hard-link aliases cannot provide independent baselines.
    try:
        same_store = os.path.samefile(previous.database, current.database)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("Cannot verify both SQLite store paths") from exc
    if same_store:
        raise ValueError("Baseline and current must be distinct SQLite stores")
    # Do not silently treat an unreadable previous store as an empty baseline.
    before = snapshot_static_design_records(previous)
    after = snapshot_static_design_records(current)
    result = verify_static_design_continuity(before, after)
    return {**result, "snapshots_audited": True, "provenance_verified": False}
