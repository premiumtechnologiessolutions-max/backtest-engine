# One synthetic integration test covering the Quant Engine control plane

`tests/test_quant_full_construction_integration.py` now connects:
1. Frozen campaign and bounded sharded DAG.
2. Durable, immutable construction DAG registry in SQLite.
3. Fenced synthetic queue claim and real Linux OS PID/group proof
   using the fixed SHA256 child only (Linux CI).
4. Native-shaped in-memory LEAN/Nautilus reports (synthetic invented prices).
5. Complete source SHA256 checks, sidecar mapping and normalized trade parity.
6. Quarantined, unverified vendor source/parity evidence in the same
   durable attempt.
7. Read-only SQLite operations/receipt integrity gate.
8. WAL-consistent backup and review-only restore.
9. Read-only mission-control snapshot: registry, parity, vendor sources,
   backup verification, explicit NO research readiness.

No original Gold archive is opened or accessed. No actual LEAN/Nautilus
engine is started. No profitability research, trading strategy, LLM model,
external provider or live market process runs. The only subprocess is a
hard-coded synthetic SHA256 worker on Linux, used to test OS supervision.

This is a functional *engineering integration test*, not acceptance of the
real-source execution engine. Critical remaining gaps include isolated
vendor execution, independent signature anchoring, complete order/fill
replay reconciliation, global multiple-testing acceptance and production UI.
