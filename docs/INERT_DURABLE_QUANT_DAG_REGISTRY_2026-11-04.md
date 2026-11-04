# Persistent inert Quant Engine DAG registry

scripts/durable_inert_campaign_registry.py binds the frozen sharded Quant
Research design to the existing durable SQLite control-plane database.
Every node and dependency is stored in a single atomic write transaction.
A registry re-check recompiles the frozen campaign and verifies every
persisted node and dependency. Missing, mutated, duplicate or extra
nodes cause an integrity error, rather than silently reconstructing them.

The registry is deliberately SEPARATE from the live research jobs table.
No worker can claim its nodes, no provider can execute from it, and no
research result can be accepted through this API. It creates metadata
for later safe workflow orchestration only.

This checks local state consistency, not data provider provenance, external
engine readiness, original Gold replay, or market profitability. Only
synthetic unit/contract tests were run during construction.