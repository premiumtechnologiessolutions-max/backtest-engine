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
    # Reject symlink aliases, including links to an otherwise valid SQLite file.
    # Pin both physical file identities before reading. Recheck after both
    # snapshots: path replacement during an audit invalidates its evidence.
    try:
        before_ids = tuple(os.lstat(store.database) for store in (previous, current))
        if not all(stat.S_ISREG(item.st_mode) for item in before_ids):
            raise ValueError("SQLite store must be a regular file")
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("Cannot verify both SQLite store paths") from exc
    if (before_ids[0].st_dev, before_ids[0].st_ino) == (before_ids[1].st_dev, before_ids[1].st_ino):
        raise ValueError("Baseline and current must be distinct SQLite stores")
    # Track both SQLite sidecars: WAL commits can bypass main-file metadata,
    # and shared-memory index replacement makes the audit environment unstable.
    def sidecar_identity(store, suffix):
        path = os.fspath(store.database) + suffix
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"SQLite {suffix[1:].upper()} sidecar must be a regular file")
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)

    try:
        before_sidecars = tuple(tuple(sidecar_identity(store, suffix) for suffix in ("-wal", "-shm"))
                                for store in (previous, current))
    except (OSError, TypeError) as exc:
        raise ValueError("Cannot verify SQLite sidecars") from exc
    # Do not silently treat an unreadable previous store as an empty baseline.
    before = snapshot_static_design_records(previous)
    after = snapshot_static_design_records(current)
    # Keep mutation detection active through continuity verification itself.
    result = verify_static_design_continuity(before, after)
    try:
        after_ids = tuple(os.lstat(store.database) for store in (previous, current))
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("SQLite store path changed during comparison") from exc
    if any((a.st_dev, a.st_ino) != (b.st_dev, b.st_ino) for a, b in zip(before_ids, after_ids)):
        raise ValueError("SQLite store path changed during comparison")
    # A stable inode does not imply stable contents: reject observable
    # in-place writes as well. WAL-only changes are NOT covered by this
    # metadata check alone; this remains non-atomic across stores.
    if any((a.st_size, a.st_mtime_ns, a.st_ctime_ns, a.st_mode) !=
           (b.st_size, b.st_mtime_ns, b.st_ctime_ns, b.st_mode)
           for a, b in zip(before_ids, after_ids)):
        raise ValueError("SQLite store metadata changed during comparison")
    try:
        after_sidecars = tuple(tuple(sidecar_identity(store, suffix) for suffix in ("-wal", "-shm"))
                               for store in (previous, current))
    except (OSError, TypeError) as exc:
        raise ValueError("Cannot verify SQLite sidecars") from exc
    if before_sidecars != after_sidecars:
        changed = "-wal" if any(a[0] != b[0] for a, b in zip(before_sidecars, after_sidecars)) else "-shm"
        raise ValueError(f"SQLite {changed[1:].upper()} sidecar changed during comparison")
    return {**result, "snapshots_audited": True, "provenance_verified": False}
