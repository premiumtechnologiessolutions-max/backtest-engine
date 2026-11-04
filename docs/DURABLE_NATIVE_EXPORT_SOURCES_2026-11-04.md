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

The two SQLite transactions are individually fenced but not one atomic
cross-table operation. If the second fails, parity remains quarantined and
unaccepted. Future production proof requires a single transaction plus
independently anchored runner signatures and order-event reconciliation.
