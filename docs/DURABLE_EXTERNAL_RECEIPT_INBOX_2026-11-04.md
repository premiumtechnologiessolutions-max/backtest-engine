# Durable external receipt inbox — ENGINEERING ONLY

A transactional receipt inbox has been added for **synthetic contract testing**
and later independent reconciliation. No external process or market strategy
is run by this component. It uses the pre-existing SQLite durable leases and
attempt history; no receiving worker can stage evidence without a CURRENT
RECONCILING lease matching the request ID, attempt ID, fencing token and
worker name inside one exclusive BEGIN IMMEDIATE write transaction.

The inbox is **not an accepted results registry**. A verified receipt only
means that supplied bytes match the provider-declared digest, canonical
queue fingerprint and attempt binding. This cannot establish that the
provider honestly executed a strategy, that source quotes were authentic,
that historical execution fields match, or that costs and accounting pass
independent audits. The artifact bytes are stored atomically in local SQLite
for later independent examination; maximum payload is 1 MiB. Big research
artifacts will require a separately audited local content-addressed store.

Core file: scripts/durable_external_receipts.py
Tests: tests/test_durable_external_receipts.py
Read-only health: scripts/durable_operations_gate.py also validates every
stored receipt and marks unverified inbox content OPERATOR_ATTENTION; corrupt
storage fails the operational gate INVALID. Ledger statuses remain unchanged,
accepted_results remains NOT_IMPLEMENTED.

Not implemented or authorized: accepting receipts as verified trading
outcomes, broker order execution, automatic worker launch, supervisor,
real Gold replay, OpenBB live fetch, strategy OOS runs or any post-construction
execution. Owner freeze: docs/ENGINE_CONSTRUCTION_FREEZE_2026-11-04.md.
