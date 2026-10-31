# Frozen Research Job — UTC Monthly Slot Planner (2026-10-28)

New **planning-only** script **scripts/research_job_month_plan.py** converts an existing
local frozen request into deterministic UTC month slots. Run locally from the
repository root:

    python scripts/research_job_month_plan.py --fingerprint <existing-64-char-request-sha256>
    python -m pytest -q tests/test_research_job_month_plan.py

The CLI first runs the existing read-only **preflight_job**: verifies queue
integrity, frozen specification and registry hashes, and exact clean Git HEAD.
It refuses partial-month evaluation windows and plans at most 120 months. Each
slot is bound to the frozen request fingerprint and half-open UTC calendar
interval by a deterministic SHA256 key. This is a **potential future checkpoint
identifier, not a checkpoint or resumable worker**.

A month is **FUTURE_OR_PARTIAL** until the first UTC instant of the following
month, then **CLOSED_SOURCE_UNVERIFIED**. Calendar closure **does not prove**
private BID/ASK source coverage, DST handling, embargo, quote-gap validity,
canonical parity, a completed backtest, or positive monthly P/L. Every slot
explicitly remains **NOT_EXECUTED**, **source_verified=false**, monthly P/L and
observed M1 floating drawdown null (display as **N/A**). No synthetic market
minutes are created. No raw data is read, no local job state is changed, and no
GitHub billing, privacy or live trading is touched.

**Important:** These UTC slots are only reporting intervals, not exchange
session boundaries. Any future worker must separately enforce the frozen
research embargo, market/DST gap policy, exact $0.40/oz roundtrip costs,
next eligible open <=1 minute, stop-first, adverse gap-through, shared
portfolio capacity, provenance and independent canonical parity before
attaching source-verified monthly metrics. A future prospective month cannot
be counted before original data are actually complete and validated.

No new Gold ZIP backtests, no new monthly P/L observations, no prospective
OOS evidence and no strategy approvals were produced by this change. PR #1
must remain Draft.
