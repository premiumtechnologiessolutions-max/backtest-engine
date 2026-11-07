# Quant Engine unified campaign blueprint — construction stage

This module is **the planned research workflow of the QUANT ENGINE**, distinct
from the SQLite job queue. It coordinates hypotheses, data provenance, reference
simulators, execution reconciliation, modeled portfolio risk, feedback and reports
through a deterministic, immutable dependency graph.

Location: `src/norisk_quant/campaign_blueprint.py`

Stages (all remain **DESIGNED_NOT_EXECUTED**):
1. Verify original market source identity (without reading original data now).
2. Align future causal market features without information leakage.
3. Freeze strategy source/spec identities.
4. Plan the No Risk FX reference executor AND optionally LEAN/Nautilus comparator.
5. Require an explicit reconciliation dependency before risk reporting.
6. Plan shared portfolio risk.
7. Plan downstream RD-Agent / TradingAgents / FinRL reviewer hooks.
8. Assemble audit-ready report dependencies.

This compiles an immutable research DAG, has strict limits on strategy count,
model fan-out and machine resource budgets, and pins the fixed all-in
USD 0.40 per ounce roundtrip fee. The compiler rejects execution flags, broker
keys, unbounded jobs, unknown providers and impossible declared evaluation
windows. There is no code execution, market-data access, strategy evaluation,
external-engine import, or AI-agent invocation.

**Important**: This is a control-plane blueprint, not an implemented or
validated provider executor or AI workflow. It does not claim that LEAN,
Nautilus, RD-Agent, TradingAgents and FinRL are installed or integrated at
runtime. Next deliverables must wire node-specific adapters to a future
supervisor and validate each isolated runner through synthetic contracts;
market research remains frozen until owner approval.

Synthetic regression: `tests/test_campaign_blueprint.py`.
Owner freeze: `docs/ENGINE_CONSTRUCTION_FREEZE_2026-11-04.md`.
