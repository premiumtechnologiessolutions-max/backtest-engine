# No Risk FX Quant Engine — construction mission-control JSON

A read-only dashboard feed is now available in
`norisk_quant.construction_mission_control.construction_snapshot` and its
offline CLI `python -m scripts.quant_construction_snapshot --design /path/design.json`.

The feed combines a fully recompiled SHA-pinned sharded design with an
optional **existing** durable SQLite operational health snapshot. It never
creates a missing database or starts worker processes, never fetches original
quote ZIPs, and has no broker or provider access. It exposes:
- Number of frozen hypotheses, shards, DAG tasks and resource ceilings.
- Difference between a referenced engine/AI reviewer and a genuinely
  installed/verified runtime (ALWAYS marked unverified here).
- Current SQLite health, jobs and unverified receipts if a database exists.
- Explicit system-wide gates still missing before owner can consider
  launching actual quant research.
- False readiness and false claims of validated profitability are prohibited.

This is a reliable structured data source for the future NRFX research UI,
not that finished UI itself. The optional CLI uses a bounded JSON reader
with duplicate-key rejection. It is a read-only construction artifact.
