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

## Optional partial-fill proof (construction-only)

The same atomic stage API now accepts `fill_events_by_engine` in memory.
If supplied, ALL planned vendor engines must provide complete per-fill
event streams; the new strict reconciliation checks quantity, entry/exit
VWAP, USD/oz fees, event chronology, identities and declared exit prices.
The resulting bounded SHA report is stored inside the same immutable
vendor source manifest as the closed-trade parity receipt. Missing or
incorrect fills cause zero receipts to be inserted.

The read-only manifest audit checks the nested fill report's SHA256,
cross-vendor completeness, source commit, per-engine normalized ledger
hashes, event counts and explicit no-attestation/no-acceptance flags.
It still cannot authenticate actual vendor runtime origin, source-side
event signatures or true market prints without a future external
supervisor. A checked fill ledger is **not** a market-research result.

Without this optional evidence, the source receipt explicitly records
`fill_event_accounting_checked=false`; this is not silently treated as
a complete event-level audit.
