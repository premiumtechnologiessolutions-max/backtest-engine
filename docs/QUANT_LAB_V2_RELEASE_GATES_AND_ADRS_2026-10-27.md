# Quant Lab 2.0 — Architecture decisions and measurable release gates

**Status: SPECIFICATION ONLY, not implementation, validation or deployment.** This complements QUANT_LAB_V2_ENGINEERING_BLUEPRINT_2026-10-27.md. Parent PR #1 remains Draft.

## ADR-001: Architecture and trusted boundaries
Use a modular Python control-plane with isolated bounded workers, not premature microservices. React/TypeScript is a client of versioned FastAPI; browser never executes strategies or calculates official P/L. The existing canonical engine owns all fills and $0.40/oz ALL-IN cost. PostgreSQL is the durable experiment ledger; private content-addressed artifacts hold reports; Parquet holds validated market partitions. No broker credentials or live order routing.

## ADR-002: Immutable run identity
Run identity = SHA256(canonical JSON of strategy AST, parameters, UTC dates, exact source SHA256, exact M1 BID/ASK fingerprint, engine Git SHA, dependency lock SHA, execution model version, cost model and random seed). Duplicate identity is idempotent. Any material change creates a new run, never overwrites an old result. Explicit versioned schema migrations and backwards-compatibility tests.

## ADR-003: Scheduling and failures
Durable PostgreSQL-backed job queue first; lease fencing token, monotonic attempt count, heartbeat and timeouts. At-least-once execution with idempotent commit of immutable artifacts, never falsely claim exactly-once execution. Atomic publish after independent reconciliation. Crash, cancel, partial write, duplicate worker and expired lease tests required. CPU/memory/time quotas, no unrestricted network or raw ZIP in frontend.

## ADR-004: Scientific integrity
Research states: proposed -> preregistered -> exploratory-tested -> robustness-tested -> sealed-OOS-evaluated -> rejected / research-candidate. Never re-label exposed years as unseen OOS. Seal untouched windows, enforce purging/embargo and time causality, count all trials and apply multiple-testing correction. Monthly win rate is a descriptive metric, not a guarantee. Cost sensitivity, drawdown, uncertainty, sample sufficiency and regime sensitivity are mandatory.

## ADR-005: Data and privacy
Raw user Gold ZIP and proprietary quotes remain private and server-side. Repository was verified PUBLIC on 2026-10-27; do not store private source data, credentials, complete trade ledgers or absolute paths in Git. Private deployment and scoped artifact authorization are hard gates. No repository visibility change without explicit owner approval.

## Acceptance gates (all must pass for release)
- **G0 baseline:** existing repo full pytest and pinned-environment build green at immutable head; no regression of existing engine contracts.
- **G1 execution:** reference/fast exact parity for discrete trade fields and specified numeric tolerances; independent 13-field original-ZIP replay completed (historical prior timeout does not count).
- **G2 provenance:** immutable source/quote/commit/lock/plan hashes; tamper and missing-year tests fail closed.
- **G3 orchestration:** 1000 synthetic jobs with injected crash, restart, cancellation, lease expiry and duplicate delivery; no lost or double-published accepted result; reconciled outputs only.
- **G4 API/security:** authorization and tenant isolation, strict schemas, pagination, rate limits, no raw paths or secret leakage; threat-model review.
- **G5 UI:** real API integration, loading/empty/error/cancel states, accessible keyboard navigation, responsive layouts, Arabic RTL and English LTR; no mock P/L in release.
- **G6 performance:** benchmark representative M1 and tick datasets against pinned baseline hardware; publish throughput, memory, latency, queue wait and cost per 1000 trials. Do not claim faster than another terminal without comparable benchmark.
- **G7 science:** preregistered forward holdout, multiple-testing accounting, outlier/gap checks and fee sensitivity; report failures and negative results.
- **G8 operations:** backups and verified restore, retention, observability, runbook, incident rollback and versioned migrations.

## Build order and definitions of done
1. Audit actual current code/UI and establish pinned test baseline.
2. Build read-only evidence registry and API, contract/security tests.
3. Connect web terminal to real evidence, with audit and bilingual accessibility.
4. Durable bounded worker queue, fault-injection and reconciliation.
5. Causal AST Strategy Factory, dedup and budgeted multi-fidelity search.
6. Validation governance and sealed forward cohorts; benchmark and document limits.
7. Pass every applicable gate before release. No auto live trading.

## Explicit limits
This document does not certify 10/10 performance, profitability, OOS, security, scalability or UI completion. It defines falsifiable tests required to earn those claims.
