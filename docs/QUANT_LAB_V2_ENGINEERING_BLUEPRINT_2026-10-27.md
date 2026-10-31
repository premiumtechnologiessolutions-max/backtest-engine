# No Risk FX Quant Lab 2.0 — Engineering blueprint (27 October 2026)

Status: architecture proposal, **not implemented or production-ready**. Parent development branch: `feat/quant-engine-foundation`; PR #1 remains Draft. PR #4 batch orchestrator was merged into this development branch, not main.

## Non-negotiable invariants
1. Canonical existing XAUUSD execution kernel remains sole source of fills, stop-first, adverse gap fills and fixed ALL-IN roundtrip $0.40/oz. No second execution model in the UI, API, or workers.
2. No real order placement. Never present synthetic OHLC fills, in-sample or exposed-year results as independent OOS or broker-certified.
3. Raw market ZIP, private plans, ledger outputs, secrets and local absolute paths must not enter Git or browser responses. Repository currently reports PUBLIC; private storage is a deployment gate.
4. Every experiment has immutable source SHA256, M1 BID/ASK fingerprint, full Git SHA, dependency lock digest, canonical plan hash, engine/version, UTC period, cost assumptions, and execution flags.
5. Rejected or incomplete reports cannot be silently promoted. No strategy is approved solely on positive months or the highest backtest score.

## Target modules and boundaries
- **Terminal UI**: React + TypeScript; read-only research overview first, then authenticated plan submission, batch monitoring, results and audit views. Never calculate P/L in browser.
- **Control API**: FastAPI, versioned `/api/v1`; Pydantic strict schemas; auth/RBAC, per-user limits, idempotency keys; only orchestrates, does not execute fills.
- **Research registry**: PostgreSQL for immutable run metadata, plan specs, statuses, evidence hashes, worker leases and audit events. Database rows reference artifacts; no full raw quotes in DB.
- **Queue/workers**: start with PostgreSQL-backed claim/lease or Redis + durable PostgreSQL state; worker invokes existing CLI/orchestrator in isolated workspace with CPU/memory/time quotas. No unbounded parallelism.
- **Artifact store**: private local object directory initially, S3-compatible later; atomic writes, SHA256, retention policy and scoped access. Raw quotes remain server-side.
- **Strategy Factory**: typed canonical AST of causally computable features, conditions, orders and risk rules; deduplicate canonical hashes, cap combinatorial explosion and track number of trials.
- **Validation**: purged/embargoed walk-forward, locked untouched forward windows, family-wise multiple-testing controls, parameter sensitivity, trade-count sufficiency and realistic cost stress.
- **Observability**: structured logs, metrics, traces, job timeline and explicit reason codes. No secrets in logs.

## First usable vertical slice
1. Read-only registry importer for existing `batch_manifest.json`, `summary.json`, `monthly.csv`, `weekly.csv`, `trades.csv`; independently verify file hashes and accounting with existing orchestrator contract. Reject unsupported schema.
2. `GET /api/v1/health`, `GET /api/v1/batches`, `GET /api/v1/batches/{id}`, `GET /api/v1/batches/{id}/experiments`, `GET /api/v1/experiments/{id}/monthly`. Paginated; read-only; no private filesystem paths in responses.
3. UI: batch list, statuses, progress, month-by-month net P/L, fees, trade count, warnings, and evidence hashes. Clearly distinguish reconciled accounting vs profitable/OOS.
4. Contract tests: schema, auth, pagination, invalid manifests, corrupted artifact hashes, no data leakage, API-to-ledger parity, empty results and retry idempotency.
5. Then add `POST /api/v1/batches` with frozen plan, explicit authorization, bounded queue, cancellation and deterministic resume; worker cannot change frozen plan after acceptance.

## State machine
DRAFT -> VALIDATED -> QUEUED -> RUNNING -> RECONCILING -> COMPLETE_RESEARCH_ONLY.
Failure paths: INVALID, FAILED, QUARANTINED, CANCEL_REQUESTED, CANCELLED. Only a worker with a valid lease can advance execution. A crash expires lease; recovery revalidates existing outputs before retry. Never mark COMPLETE until manifest and every period ledger reconcile.

## Security and reproducibility gates
- Keep deployment private by default; repository visibility must be checked separately and corrected only with explicit owner authorization.
- Authenticated users, least privilege, CSRF/CORS controls, rate limits, API audit events; artifact downloads signed/scoped and expiring.
- Workers run without trading credentials, outbound broker access or privileged filesystem mounts.
- Fail closed on mismatched source SHA, checkout SHA, dependency lock, plan hash, calendar-month coverage or accounting; immutable manifests.
- Pin Python/JS dependencies; SBOM and CI static analysis; no remote production launch without independent replay and security review.

## Milestone acceptance
M0: map existing code, tests and actual UI assets, preserve all engine parity gates.
M1: registry importer + read-only API + tests; all legacy fixtures unchanged.
M2: actual web UI consuming M1 endpoints; no mock numbers in production UI.
M3: bounded asynchronous queue and resume; end-to-end synthetic original-CLI smoke with crash/retry tests.
M4: Strategy Factory typed AST, dedup, controlled parameter grids, test budget.
M5: forward/OOS governance and documented real-source 13-field replay. Still research-only until broker-specific execution and risk validation.

## Explicitly NOT claimed
No new code for UI/API/worker has been implemented by this blueprint alone; no CI or original Gold ZIP replay was run for this document; no profitable strategy or autonomous continuous service is certified.
