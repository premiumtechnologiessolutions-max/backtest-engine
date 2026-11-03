# Engineering review handoff: evidence, architecture decisions, and release blockers (2026-11-03)

Status: **DRAFT FOR INDEPENDENT REVIEW; NOT APPROVED FOR DEPLOYMENT**.
Scope: branch `feat/quant-engine-foundation`, PR #1, observed head `0d0052724ce205231d599978c8744ebd9eba551c`.
No trading, broker orders, source archive upload, or changes to repository visibility are authorized by this document.

## Verified at review time

- GitHub repository visibility: **PUBLIC**, despite prior descriptions as private. Do not commit original quotes, credentials, full private ledgers or host paths.
- PR #1: **Draft, unmerged**.
- On the observed head, GitHub reports **success** for both `Engine quality gates` and `Quant Lab — causal formula regression`. This is CI evidence, not an original-archive replay.
- Canonical source boundary: `norisk_quant.data`; frozen batch entry: `scripts.research_batch_orchestrator.run_plan`; arithmetic pipeline: `scripts.run_quant_research_platform.run_pipeline`; director: `scripts.research_autonomous_director.drive`; unattended host supervisor: `scripts.research_unattended_service.serve`; local console: `scripts.quantlab_desktop.ResearchHub`.
- The multi-family batch runner, arithmetic director, and local console **do not yet share one durable scheduler/state/evidence contract**.
- The original 2012 689-trade/13-field comparison is **historical evidence from a prior run**, not a current-head replay. Do not promote a timed-out multi-year run to a pass.
- Historical exposed BOS/H1 and quote-gap studies were negative; neither demonstrates OOS profitability. No independently validated live trading edge is claimed.

## Architecture decision register (reviewer sign-off required)

| ID | Decision | Current evidence | Required decision and acceptance |
|---|---|---|---|
| A01 | One authoritative execution engine | Frozen historical runner and reference/fast checks exist | Identify single owner of fills, stop-first, gap-through, same-entry exits, and XAUUSD $0.40/oz ALL-IN roundtrip; parity tests prohibit UI/worker alternate P/L. |
| A02 | One job state machine | Multiple orchestrators and local UI exist | Define immutable job IDs, plan/source/commit/lock hashes, exclusive claim with fencing, heartbeat, cancellation, recovery, atomic reconciliation and publish. |
| A03 | Durable metadata store | Prior blueprints conflict on PostgreSQL vs lightweight local-first storage | Decide explicit deployment phase: local single-host SQLite or PostgreSQL; specify migration trigger, concurrency and restore tests. Do not claim both are approved. |
| A04 | Private evidence storage | Source archive is private; repo is public | Content-addressed private artifacts, SHA verification, scoped reads, retention, audit log, path redaction, backups and restore drills. |
| A05 | Strategy proposal boundary | External formula JSON intake exists; vendor runtimes not integrated | Restrict to typed causal AST/allowlisted parameters; generator cannot submit fitness, Python code, orders or OOS results. Require provenance attestation for third-party claims. |
| A06 | Scientific validation | Exposed historical results and synthetic fixtures exist | Freeze untouched prospective holdout before observing it; purged/embargoed walk-forward, family-wise trial accounting, cost stress and failure reporting. |
| A07 | Data ingestion | Original XAUUSD BID/ASK and read-only OANDA candle adapter exist | Enforce quote geometry, UTC, provenance, gaps, side-specific spreads and calendar; never equate candles to broker fills. |
| A08 | Resource isolation | Bounded local supervisors exist | OS-managed host, CPU/RAM/disk/time quotas, kill/restart drill, lease fencing, nonprivileged workers and no broker secrets. |
| A09 | API/UI authority | Local console and offline dashboards exist | Read-only evidence API first, no mock P/L; choose auth/RBAC before multiuser API, responsive RTL/LTR and reconciliation provenance. |
| A10 | Multi-asset scope | Read-only signal-intent research exists | Keep instrument-specific execution and cost models; never reuse XAUUSD fee model for EURUSD. |
| A11 | Security/repository posture | Public GitHub, no production host certified | Threat model, dependency pins/SBOM, secret scan, private artifact boundary, reviewer approval and incident runbook. |
| A12 | Release policy | PR Draft and CI green on observed head | Keep Draft until original ZIP current-head 13-field replay, full pinned CI, end-to-end recovery, independent scientific and security review. |

## Canonical proposed research lifecycle

1. PROPOSE: typed hypothesis, generator identity and trial budget; no self-reported score.
2. FREEZE: immutable source SHA256, BID/ASK fingerprint, Git SHA, dependency lock, cost model, strategy AST, UTC periods and seed.
3. QUEUE: durable claim with fencing token, bounded resources, explicit no-live-order credentials.
4. EXECUTE: only canonical reference/fast execution engine computes fills and fees.
5. RECONCILE: trades, equity, monthly/weekly ledgers, quote gaps and reference parity; quarantine any mismatch.
6. DECIDE: reject or research-only candidate; never reinterpret exposed years as unseen.
7. LEARN: generator sees audited training diagnostics only, not sealed forward results.
8. PUBLISH: immutable signed/hashed evidence; read-only UI displays state and limitations.
9. RECOVER: after crash, validate source and existing outputs before idempotent resume.

## Blocking independent review evidence

- **E1:** pinned full repository CI at exact review SHA (already green on observed head; re-run on any subsequent commit).
- **E2:** authorized private original Gold ZIP exact SHA `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` replay, 2012 689 trades x 13 fields, current checkout; publish only aggregate receipt and no raw source.
- **E3:** 1000 synthetic jobs with crash, lease expiry, duplicate delivery, cancel and resume; no lost/double-published accepted results.
- **E4:** security review of read-only API, auth, secrets, private artifacts and path leakage.
- **E5:** actual host power-cycle/kill/restart evidence, not only mocked tests.
- **E6:** preregistered untouched prospective evaluation; no guarantee of positive months.
- **E7:** unified UI/API/queue integration test showing only reconciled results and explicit non-ready states.

## Reviewer questions

1. Is one canonical execution authority enforceable across every strategy family and asset?
2. Is the proposed job identity sufficient to reproduce a run after dependency/data changes?
3. Which storage choice minimizes risk for the **first** deployment, and what objective load requires migration?
4. Can any generator access sealed holdout, alter costs, fabricate fitness or place an order?
5. Which failure modes can cause a false `COMPLETE` status?
6. Which original-data, broker-fill, security and operational evidence must be supplied before any production approval?

**Release conclusion:** REVIEWABLE ENGINEERING BASELINE ONLY. CI success does not mean platform-ready, always-on, independently OOS validated, or live-trading safe.
