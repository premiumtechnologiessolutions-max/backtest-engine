"""Read-only operational readiness gate for the durable research control plane.

Exit 0: metadata internally consistent and no operator-action condition.
Exit 2: internally consistent but paused/expired/cancel-requested work exists.
Exit 3: corrupt, inaccessible or inconsistent metadata (fail closed).

No worker starts, no database state transitions, no research certification.
The database must already exist: opening a missing DB is an error, not an
instruction to initialize one. Designed for a local watchdog/CI probe.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from scripts.durable_research_state import DurableResearchState

SCHEMA = "NRFX_DURABLE_OPERATIONS_GATE_V1"


def evaluate(database: Path, *, now_ms: int | None = None) -> tuple[int, dict]:
    path = Path(database)
    if (not path.is_file() or path.is_symlink() or path.parent.is_symlink()):
        return 3, {"schema": SCHEMA, "status": "INVALID", "reason": "unsafe_or_missing_database"}
    try:
        # Avoid DurableResearchState.__init__, which creates/migrates schema.
        # SQLite read-only URI mode prevents a monitoring probe from writing.
        import urllib.parse
        uri = "file:" + urllib.parse.quote(str(path.resolve())) + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as db:
            db.row_factory = sqlite3.Row
            check = db.execute("PRAGMA integrity_check").fetchone()
            if check is None or check[0] != "ok":
                raise ValueError("SQLite integrity check failed")
            db.execute("PRAGMA query_only=ON")
            # Pin audit and inventory to ONE SQLite read transaction. Separate
            # connections can observe different commits between checks, making
            # a healthy audit appear to certify an unaudited newer snapshot.
            # BEGIN starts the snapshot at the first subsequent SELECT.
            db.execute("BEGIN")
            class ReadOnly(DurableResearchState):
                def __init__(self):
                    self.database = path

                def _connection(self):
                    from contextlib import contextmanager
                    @contextmanager
                    def connect():
                        yield db
                    return connect()

            probe = ReadOnly()
            try:
                audit = probe.audit_integrity()
                snapshot = probe.operational_snapshot(now_ms=now_ms)
                from scripts.durable_receipt_inventory import audit_all_external_receipts
                receipt_audit = audit_all_external_receipts(probe)
            finally:
                db.execute("ROLLBACK")
        # Never interpret a boolean success of the audit as a trading result.
        if not isinstance(audit, dict) or not isinstance(snapshot, dict):
            raise ValueError("Unexpected operations audit shape")
        payload = {"schema": SCHEMA, "status": "HEALTHY", "audit": audit,
                   "operations": snapshot, "receipt_inbox": receipt_audit,
                   "research_edge_proven": False}
        # Operational snapshot's action-required signal is authoritative.
        # Also examine status counts for cancellation regardless of clock.
        counts = snapshot.get("by_state", {})
        if not isinstance(counts, dict):
            counts = {}
        action = bool(receipt_audit["unverified_receipts"]) or (
            bool(snapshot.get("requires_operator_attention"))
                  or bool(snapshot.get("operator_attention"))
                  or any(counts.get(s, 0) for s in ("CANCEL_REQUESTED", "QUARANTINED")))
        # Some snapshots expose a list of actionable expired leases.
        action = action or any(
            isinstance(snapshot.get(k), (list, dict)) and bool(snapshot[k])
            or isinstance(snapshot.get(k), int) and snapshot[k] > 0
            for k in ("expired_leases", "expired_active_leases", "expired_active_or_cancel_leases", "attention_required")
        )
        if action:
            payload["status"] = "OPERATOR_ATTENTION"
            return 2, payload
        return 0, payload
    except (sqlite3.Error, ValueError, TypeError, KeyError, OSError) as exc:
        return 3, {"schema": SCHEMA, "status": "INVALID",
                   "reason": type(exc).__name__}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    args = parser.parse_args(argv)
    code, payload = evaluate(args.database)
    print(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
