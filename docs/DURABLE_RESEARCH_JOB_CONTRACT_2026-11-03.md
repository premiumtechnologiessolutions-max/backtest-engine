# Durable research job contract v0.1 — implementation specification (2026-11-03)

Status: PROPOSED, not implemented or approved. PR #1 stays Draft. This document turns handoff A02/A03/A04 into testable contracts without claiming the current orchestrators comply.

## Identity and provenance
A job's immutable identity is SHA256 of canonical JSON (sorted keys, UTF-8, fixed decimal serialization, UTC ISO8601 timestamps) containing: schema_version, experiment_id, strategy_ast_sha256, data_source_sha256, bid_ask_fingerprint, git_commit_sha, dependency_lock_sha256, execution_policy_sha256, cost_policy_sha256, period_start_utc, period_end_utc, random_seed. Never include local absolute paths or secrets. Distinguish job_id from attempt_id (UUID), and output_receipt_sha256 from either.

## Authoritative state machine
PROPOSED -> FROZEN -> QUEUED -> RUNNING -> RECONCILING -> ACCEPTED | REJECTED | QUARANTINED.
RUNNING -> RETRY_WAIT on recoverable failure; RETRY_WAIT -> QUEUED. QUEUED/RUNNING/RETRY_WAIT -> CANCEL_REQUESTED -> CANCELLED. Terminal states are immutable; a rerun creates a new attempt or a new job if identity inputs change. REJECTED means scientifically negative; QUARANTINED means invalid/incomplete evidence. Never label either successful trading research.

## Transaction boundaries
- Persist FROZEN with canonical JSON and hashes before queueing; never mutate frozen inputs.
- Claim QUEUED using atomic compare-and-swap; lease has monotonically increasing fencing token and expiry. Every heartbeat, result write and finalization must check current token.
- Write outputs to private temporary attempt namespace; verify source hashes, accounting, execution parity, complete manifest, and costs before publishing.
- Commit ACCEPTED and immutable receipt reference in one metadata transaction; artifacts must already be durable. Consumers only read ACCEPTED receipts.
- On crash, expired lease may be reclaimed; old worker with stale fencing token cannot publish. Garbage-collect orphaned temporary outputs after retention window.
- Cancellation is cooperative with forced worker termination after deadline, and must never publish partial performance.

## Minimum metadata tables (logical, backend-agnostic)
jobs(job_id PK, frozen_manifest_sha, state, created_utc, updated_utc, version);
attempts(attempt_id PK, job_id FK, attempt_no, fencing_token, lease_expires_utc, worker_id, state, error_code);
receipts(receipt_sha PK, job_id UNIQUE FK, attempt_id FK, manifest_sha, published_utc);
events(event_id PK, job_id FK, attempt_id nullable, transition, timestamp_utc, prior_version, new_version);
holdout_registry(holdout_id PK, source_hash, sealed_start_utc, sealed_end_utc, preregistration_hash, access_policy).
Use transactional uniqueness and durable writes; SQLite single-writer is an option for single-host pilot, not an already approved decision.

## Acceptance tests (must be executable before approval)
T01 duplicate enqueue x1000 => exactly one job identity, at most one ACCEPTED receipt.
T02 two workers race claim => one lease owner, strictly increasing fencing tokens.
T03 worker A pauses past lease; B reclaims; A resumes => A cannot write/publish.
T04 kill after artifact write before DB commit => no ACCEPTED until verified retry.
T05 kill after DB commit before notification => idempotent notification; one receipt.
T06 source BID/ASK fingerprint changes => hard quarantine, never silent re-run.
T07 dependency lock or cost model changes => distinct job_id.
T08 incomplete monthly/weekly accounting or fee != 0.40 USD/oz canonical XAUUSD => quarantine.
T09 cancellation at each state => no accepted partial receipt.
T10 malformed generator AST, self-reported fitness, or Python payload => reject before queue.
T11 sealed holdout queried by generator => deny and audit.
T12 host restart + DB restore => no duplicate accepted jobs, receipts resolve and hash-verify.
T13 original authorized 2012 ZIP current-head replay => 689 trades x 13 fields; failure if mismatch; never ship source archive.
T14 UI/API receives only reconciled receipts; missing source or stale heartbeat => NOT READY.
T15 bounded resource exhaustion => worker killed, state recoverable, no unbounded retry loop.

## Release evidence format
Each test receipt records exact Git SHA, environment lock hash, timestamp UTC, fixture/source hash (not source bytes), invocation, exit status, assertion counts, log hash and reviewer. Synthetic tests are explicitly marked SYNTHETIC; archived original replay is HISTORICAL; sealed forward tests are OOS only if preregistered before access.

## Scope guardrails
No live broker orders, no secret exposure, no repository visibility change, no fabricated CI/replay pass. Prior BOS/H1 and quote-gap negative controls remain rejected. This contract is a specification, not evidence that any acceptance test passed.
