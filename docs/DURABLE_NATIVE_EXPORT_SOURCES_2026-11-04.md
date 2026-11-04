# Durable native source evidence

The strict source-shaped LEAN/Nautilus conversion now connects to the
existing fenced SQLite cross-engine parity inbox via
`scripts.durable_native_export_sources.stage_native_source_evidence`.

The function computes real per-row parity from supplied local source-shaped
bytes, then stores the parity receipt and an immutable hash-only vendor
source manifest for the same fenced attempt. A read-only audit crosschecks
attempt, fencing token, report identity, vendor pin and normalized SHA.

No private prices or Gold archive are stored in this metadata receipt.
All source and result claims remain UNVERIFIED: neither a self-supplied
export hash nor a favorable comparison establishes that a vendor process
actually ran.

The parity receipt and native source manifest are now committed under ONE
SQLite BEGIN IMMEDIATE transaction. Either both rows commit or BOTH roll
back if the second insert fails. Repeated identical requests are
idempotent; concurrent requests serialize on the SQLite write lock. An
old, stand-alone parity receipt WITHOUT its vendor source manifest is
BLOCKED for manual review rather than silently completed with new bytes.

The standalone parity-only API remains available for synthetic comparison
diagnostics and does not claim a vendor source was bound. Existing
historical partial source records are not automatically migrated.

This removes the partial-publication gap, but it does NOT independently
authenticate vendor execution, sidecar preregistration, raw fill events,
or real price provenance. Those remain production acceptance blockers.
