# No Risk FX Quant Engine — engineering-first freeze (2026-11-04)

## Binding owner decision

**DO NOT RUN THE RESEARCH ENGINE BEFORE ENGINEERING COMPLETION.**

The owner explicitly requested construction and code integration first, with no real Gold market backtests, training/validation/OOS campaigns, multi-year replays, LEAN/Nautilus external engine execution, OpenBB live fetches, RD-Agent/TradingAgents/FinRL runs, live brokerage connections, or automated research workers until the complete platform passes the engineering readiness review and the owner explicitly authorizes a separate execution stage.

**Permitted while constructing:** reading and reviewing source, pinned Git/submodules, original engineering code, dependency checks, static analysis, compilation, narrowly scoped synthetic unit/contract tests and GitHub CI on synthetic fixture data. These are software construction tests, not strategy/market research runs. Do not run commands whose test fixtures access real broker accounts or original Gold archives. Never silently expand synthetic CI into historical market execution.

Do not publish the private original Gold ZIP, credentials, private outcome ledgers or sensitive material. Do not alter repository visibility or spending. Keep Draft PR #1 open and unmerged. Any existing research result belongs to historical context only; it must not be presented as new OOS or engine readiness evidence.

## Definition of engineering complete (all required, no percent based on file count)

1. **Master architecture and data flows:** source provenance; system boundaries; module ownership; interfaces, schemas and lifecycle diagrams across data, strategy, backtest, AI, scheduler, audit, terminal.
2. **Data engineering:** immutable BID/ASK and optional tick-source manifests, bounded ingest, complete temporal/currency calendars, missing-minute and crossed-quote handling, versioned materialization and read-only provider adapters.
3. **Research execution core:** deterministic time ordering; position and cash accounting; one canonical USD/oz fee policy; limits and multi-strategy arbitration; independently testable reference and fast paths; no lookahead.
4. **Third-party integration audit:** source-level review and tested, isolated provider-specific adapters for only beneficial components from LEAN, NautilusTrader, OpenBB, RD-Agent, TradingAgents, FinRL (and subsequently any verified user-owned Terminal). Git submodules alone do not count as integration.
5. **AI hypothesis factory:** bounded proposals, frozen hypotheses, provenance, feedback-memory, multiple-testing control, evaluation policies, human-inspectable decisions. Never allow an AI agent to set ACCEPTED or open broker orders.
6. **Control plane:** durable job state + leases + fencing, operating-system worker identity and process supervisor, interruption/cancellation semantics, bounded concurrency, quotas and crash recovery. Avoid parallel schedulers claiming the same workload.
7. **Result attestation:** atomic verified-receipt publish/accept transition, authentic source chain, independent execution-field parity verifier, complete month/week/equity accounting, rejection/quarantine, recovery from interrupted writes, traceable audit events.
8. **Research interface and reporting:** one integrated UI for campaign design, provider status, job states, uncertainty/quality flags, metrics, drilldowns, evidence export, failure diagnostics, resume and access roles, without unsupported backtest success claims.
9. **Operational resilience & security:** backups/restores, secrets isolation, dependency/license provenance, rate limits, monitoring/alerts, error budgets, resource benchmarks on synthetic fixtures, supply-chain and threat review.
10. **Engineering acceptance:** pinned environment, full repository Python tests, isolated adapter contract suites (including negative/failure injection), end-to-end **synthetic** workflow, independent multi-review audit, documented release checklist.

Until every line has reviewed testable evidence, the state is **CONSTRUCTION / NOT READY**, and no real market replay or external engine run is authorized by this document.

## Later phase — explicitly separate

Only **after** engineering completion and explicit new owner approval: run original market ZIP validation, exact 13-field independent parity, real historical research, preregistered forward/OOS evaluation and independent performance adjudication. This later research is not part of the construction stage. Successful software CI alone does not establish a trading edge or monthly profitability.

## Current evidence boundary

Existing `external_research_bridge.py`, `external_queue_binding.py`, `causal_stream_merge.py`, `openbb_fred_snapshot.py`, `gold_macro_replay.py`, and `research_gold_macro_context.py` establish bounded subcomponent contracts; full external engines and independent production acceptance are not complete. Mark each component integrated only when its own actual interface/CI tests exist. Never call a source-linked upstream engine executable unless the owner separately authorizes a research-execution phase.
