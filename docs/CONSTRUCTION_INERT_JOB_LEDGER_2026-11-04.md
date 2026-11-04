# Construction-only inert job ledger — 2026-11-04

## Scope
`scripts/construction_job_ledger.py` stores admitted construction job descriptors in memory and deduplicates by the existing canonical SHA-256 fingerprint. It **does not** enqueue, dispatch, execute, persist, or access market data. Immutable snapshots are sorted by fingerprint. Changing source commit creates a different identity.

## Verification
`tests/test_construction_job_ledger.py` contains five synthetic-only tests: inert state, duplicate suppression, forbidden market-job rejection, source-commit separation, and immutable snapshots. Locally, these five passed in an isolated harness with matching copies of the two upstream admission/fingerprint modules; repository-wide CI must independently verify integration.

## Limitations and acceptance
In-memory storage is intentionally not durable, not multi-process safe, and not an authorization boundary. Do not attach workers or a scheduler. Before any production queue, require transactional durable uniqueness, atomic claim/lease/expiry, role-based access, crash recovery, audit trail, read-only dry-run mode, resource quotas, explicit execution approval, and synthetic integration tests. Construction-only policy remains in force: no real XAUUSD data, market backtests, external framework runs, or live trading.

At the time of this change, latest inspected GitHub Actions for head `924dcc19` showed Quant Lab success but Engine quality gates failure. Do not represent this as complete CI success. Draft PR #1 remains unmerged.
