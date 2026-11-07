# Durable research control plane — WAL-safe backup and gated restore

Construction deliverable: `scripts/durable_backup_attestation.py`

What this adds:
- SQLite `Connection.backup()` takes a consistent read-only snapshot of the
  durable control plane, including committed WAL writes. Do not copy a live
  SQLite main file by itself: that can omit WAL data.
- A snapshot is staged inside a private temporary directory, verified with
  the existing full read-only operational health gate, and published as a
  directory containing `state.sqlite3` and SHA256-protected
  `manifest.json`. A snapshot ID is never intentionally overwritten.
- Reverification checks canonical exact-schema manifest fields, both file
  hashes, and independently reruns the read-only control-plane gate at the
  frozen original capture clock.
- Restore is permitted ONLY to a new SQLite path and preserves old
  jobs/attempts/fencing tokens/receipts byte-for-byte. A restored
  RUNNING/RECONCILING task is NOT automatically resumed, claimed, cancelled,
  or marked complete. Operator and independent OS process-exit review
  remain compulsory.

**Important limits**:
1. SHA256 plus a modifiable manifest is *integrity detection*, not
   independently trusted signing. Separate signed backup manifest,
   encrypted off-host storage and access controls remain necessary.
2. Backups contain internal research contracts, receipts and possibly
   payload bytes, so do not publish backup directories to public GitHub,
   upload market data, or expose them on a server.
3. No worker process is launched, and tests use synthetic SQLite job and
   receipt metadata only. This does not constitute recovery from a real
   market-data replay or full platform readiness.
4. Multi-host orchestration, backup retention policy, cross-platform
   crash recovery and external append-only attestation remain incomplete.
5. Restore uses the current software version's read-only gate. An upgraded
   incompatible schema must be explicitly migrated and audited, not
   silently accepted.
6. Backup directory publishing assumes a trusted private local filesystem
   and cooperative writers. A later OS-level immutable store or openat2
   directory-handle approach is needed for untrusted shared filesystems.

The owner has restricted all work to **ENGINE CONSTRUCTION ONLY**. Do
not use this module to resume research or to open real Gold archives.
