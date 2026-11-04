"""Read-only construction ledger manifest; never dispatches or evaluates jobs."""
import hashlib
import json

from scripts.construction_job_ledger import ConstructionLedger


def manifest(ledger):
    """Produce reproducible metadata, explicitly NOT a completed-run report."""
    if not isinstance(ledger, ConstructionLedger):
        raise TypeError("Expected an inert ConstructionLedger")
    entries = ledger.snapshot()
    records = []
    seen = set()
    for entry in entries:
        if (type(entry.digest) is not str or len(entry.digest) != 64
                or any(c not in "0123456789abcdef" for c in entry.digest)
                or type(entry.source_commit) is not str
                or len(entry.source_commit) != 40
                or any(c not in "0123456789abcdef" for c in entry.source_commit)
                or entry.state != "RECORDED_NOT_EXECUTED"
                or entry.digest in seen):
            raise ValueError("Invalid inert ledger entry")
        seen.add(entry.digest)
        records.append({"fingerprint": entry.digest,
                        "source_commit": entry.source_commit,
                        "state": entry.state})
    records.sort(key=lambda record: record["fingerprint"])
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"schema_version": 1, "mode": "ENGINE_CONSTRUCTION_ONLY",
            "execution_started": False, "market_data_accessed": False,
            "completed_jobs": 0, "monthly_pnl": None,
            "floating_drawdown": None, "recorded_specs": len(records),
            "records_sha256": hashlib.sha256(encoded).hexdigest(),
            "records": records}
