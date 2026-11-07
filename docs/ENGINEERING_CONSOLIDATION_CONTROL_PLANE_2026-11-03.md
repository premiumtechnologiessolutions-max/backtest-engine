# No Risk FX Quant Engine — Engineering Consolidation, Phase 1

Date: 2026-11-03. Work only on `feat/quant-engine-foundation`; PR #1 remains Draft.

**Research-only.** This is NOT evidence of profitability, a deployed 24/7 host,
broker tick fills, or independent OOS validation. The source archive is local:
SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
GitHub currently reports this repository as **public**. No source ZIP,
credentials, private ledger, billing or visibility changes belong in this work.

## Actual boundaries and owners

| Boundary | Canonical current entry point | Scope |
| --- | --- | --- |
| Source | `norisk_quant.data` | Original M1 BID/ASK and UTC/SHA validation |
| Frozen family batches | `scripts.research_batch_orchestrator.run_plan` | Bounded plan -> historical audited ledgers |
| Arithmetic generation | `scripts.run_quant_research_platform.run_pipeline` | Bootstrap -> generation -> training feedback -> dashboard |
| Arithmetic director | `scripts.research_autonomous_director.drive` | Bounded, resumable formula generation |
| Host supervision | `scripts.research_unattended_service.serve` | OS-owned status, retry budget and lock |
| Health authority | `scripts.research_unattended_healthcheck.evaluate` | Heartbeat plus cross-check of completion with director |
| Console | `scripts.quantlab_desktop.ResearchHub` | Local operator-driven frozen batches |
| Historical registry | `research/strategy_factory_registry.json` | Exposed historic metadata, not live/OOS proof |

**Do not conflate processes:** the multi-family grid, local batch UI and
arithmetic evolutionary campaign do not yet share one scheduler. Local UI
autopilot is a bounded daemon thread, NOT a host-resident service.

## Fixed operational truth contract

Previously the console labeled the whole `platform_ready` when merely
configured with source path and clean Git checkout; the source could have
changed since configuration. The UI now distinguishes:

- `source_configured`: a path is saved; not proof of current SHA.
- `source_verified_now`: the file currently matches authorized SHA256.
- `batch_runner_ready`: valid source + clean exact-code checkout.
- `platform_ready`: false pending real cross-system acceptance.
- `autonomous_research`: status only from the existing health validator,
  optionally linked via `--autonomous-root /absolute/private/output`.

This health link is **read-only**. It does not deploy/start/restart a host,
share quotes, or interpret historic training as clean OOS. Stale/missing/
malformed heartbeat remains non-healthy; no green inferred from directory
existence or a prior successful run.

## Required end-to-end research lifecycle

1. **Propose:** family, immutable rule definition, training cutoff, hypothesis.
2. **Freeze:** source SHA + exact code commit + fixed $0.40/oz cost + embargo.
3. **Run:** explicit resource budget and process lock, no broker/live trading.
4. **Reconcile:** trades, observed equity, missing quote gaps, monthly/weekly,
   reference-vs-fast when supported and legacy 13-field parity when available.
5. **Decide:** reject/quarantine or freeze a genuinely future OOS evaluation.
6. **Learn:** only audited training feedback may propose the next experiment.
7. **Persist:** immutable audit trail, durable checkpoints and failure states.
8. **Observe:** UI reads canonical evidence; it must not invent green status.

## Release gates (blocking, not documentation milestones)

| Gate | Acceptance evidence | Status |
| --- | --- | --- |
| G0 code | exact-head constrained pytest, compile, smoke CI | rerun on new commit |
| G1 original parity | private original ZIP, current official checkout, 2012 689 trades x 13 fields | pending latest-head run |
| G2 host reliability | real server, power-cycle/kill/resume drill, exclusive writer | code exists; no real host acceptance |
| G3 orchestration | one job/state/evidence contract across factory and arithmetic research | phase 1 shares only verified host health |
| G4 science | preregistered future holdout, independent audit, multiple-testing control | no proven OOS edge |
| G5 product | one integrated UI spanning all families, queues and auditable outcomes | local UI and separate reports exist |

Never merge PR #1 or claim a production-ready autonomous Quant Engine
from a successful synthetic CI run alone.
