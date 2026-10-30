# No Risk FX Unified Research Platform — Batch 04

Date: 2026-10-30. **Draft research-only architecture and implementation**, independently testable without importing the private AI Quant Lab repo.

## Motivation and inspected source

AI Quant Lab V4 implements a nine-stage campaign run by Atlas:
Vega Data Intelligence -> Iris Regime -> Oracle capability audit -> Nova Hypothesis ->
Chronos Backtest -> Sentinel Quant Audit -> Aegis Risk -> Forge evolution ->
Echo reporting. It has durable SQLite, named agents, Thompson-sampled selections,
Qualitative LLM proposals, and demo-only MT5 safeguards. Source examined:
premiumtechnologiessolutions-max/aiquantlab, README, src/ai_quant_lab/institutional/program.py,
institutional/registry.py, institutional/brain.py, runtime/lab.py.

The canonical XAUUSD engine has its *own* ExperimentIdentity and fingerprint in
src/norisk_quant/registry.py, and does not yet contain a verified automatic
observed-tick executor. This bridge therefore must not import AI Quant Lab's
Quant Score, PBO approximation, unrealized trades, or trading permissions.

## Delivered in this batch

- src/norisk_quant/research_control_plane.py:
  - Exact VERSIONED input JSON mapping for Nova/Forge numeric hypothesis proposals,
    fixed dataset SHA and 40-character Git commit, bounded XAUUSD parameters,
    explicit UTC experiment windows, known historical exposure, pinned cost
    $0.40 per ounce ALL-IN roundtrip in **canonical experiment identity**.
  - Deduplicate same canonical experiment across AI agents and campaign IDs.
    Repeating a search in the same exposed window cannot masquerade as independent evidence.
  - Durable **PAUSED BY DEFAULT** SQLite queue, WAL-compatible transactional journal,
    random lease bearer tokens stored as hashes, claim attempt fencing, bounded
    four active leases, 10–3600 second leases and three attempts maximum.
  - Crash restart restores jobs, expires abandoned leases, and can reassign
    stalled work without allowing the old worker to publish a result.
  - Operator pause revokes active leases immediately; resume is explicit.
  - Completion persists **only unverified artifact SHA or rejection reason**.
    An agent may never set official P/L, paper/live authorization, OOS,
    broker fills, or risk approval.
  - Read-only status/audit methods exclude strategy parameters, broker
    credentials, hashes of source raw content and lease secrets.
- tests/test_research_control_plane.py:
  - Canonical registry matching, dedup, invalid proposals/guardrails.
  - Worker lease timeout, pause/resume, restart recovery and exhausted retry budget.
  - SQLite transactional rollback after injected failures and concurrent file handles.
  - Bounded 4-way worker operations, 60-job restart exercise, privacy projections.
- .github/workflows/unified-research-control-plane.yml: Python 3.12
  Linux+Windows targeted tests and Linux canonical full suite.

## Important security / scientific limits

- The consumer is an **offline research proposal queue**, not an AI Quant Lab
  agent adapter or live scheduler integration. A later *private* runner needs
  to bind AI Quant Lab campaign events to this versioned input contract.
- Queue state 'completed' means **unverified research artifact recorded**,
  never "profitable strategy" or a passed audit. External artifact SHA merely
  identifies what the worker claimed to write; it is not a verified ledger.
- A dataset SHA is a *claimed identity*, not proof of a valid original/private
  Data Hub manifest. Integrate this with B02 source registry at a later gate.
- The persisted queue is one local filesystem SQLite database. No distributed
  consensus, independent isolated sandbox for LLM-generated executable code,
  job cancellation signalling, or HA failover in this batch.
- The controller deliberately does not call broker APIs, generate strategies,
  execute backtests, load original Gold M1, publish to Oracle, or expose an API.
- Before real runner use, add a versioned worker-output evidence attestor,
  isolation boundaries, source-manifest preflight, cost reconciliation,
  and 1,000+ process termination/restart injection tests.

## Follow-on acceptance

1. Independent CI green on exact PR head across Linux/Windows.
2. Provenance-bound Data Hub source manifest adapter; strict 'original_gold_m1_bidask'
   vs 'private_terminal_bidask_ticks' separation (B01–03).
3. Actual read-only AI Quant Lab task exporter with no secrets or mutable state
   crossing the interface; explicit versioned Atlas/Forge/Nova mapping.
4. Attach verified canonical runner to claims; verify evidence, negative months,
   multiple-testing counts and OOS labeling **outside the AI narrative**.
5. Build private authenticated Terminal status dashboard only after the
   worker is reliable and database backups/restore are verified.

Parent epic #6. Do not merge/deploy this PR as production or trade eligibility.