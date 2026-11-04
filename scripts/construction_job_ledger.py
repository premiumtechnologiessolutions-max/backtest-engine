"""Inert, in-memory construction-only ledger. No job execution or disk I/O."""
from dataclasses import dataclass
from scripts.construction_job_fingerprint import fingerprint


@dataclass(frozen=True)
class LedgerEntry:
    digest: str
    source_commit: str
    state: str = 'RECORDED_NOT_EXECUTED'


class ConstructionLedger:
    def __init__(self):
        self._entries = {}

    def record(self, spec):
        """Deduplicate admitted descriptors; never dispatch them."""
        identity = fingerprint(spec)
        digest = identity['job_fingerprint']
        if digest not in self._entries:
            self._entries[digest] = LedgerEntry(digest, identity['source_commit'])
        return self._entries[digest]

    def snapshot(self):
        """Return immutable, deterministic records without exposing mutable state."""
        return tuple(self._entries[k] for k in sorted(self._entries))
