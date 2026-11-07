# Canonical monthly ledger coverage gate — 2026-10-30

## Problem and implementation

A source-reconciled batch can have a correct total for the **observed** monthly rows while silently omitting a requested UTC calendar month. The monthly risk routine already reset nonpositive streaks and 3-month windows at gaps, but the scorecard could still present incomplete monthly coverage without a clear failure.

`scripts/research_batch_monthly_scorecard.py` now enumerates every requested UTC calendar month, including partial edge months, and exposes `missing_requested_calendar_months_utc` and `requested_calendar_month_coverage_complete`. The **canonical scorecard rejects** an audited job with any missing requested month, rather than treating absent evidence as a zero-trade or zero-profit month. Monthly windows longer than 361 months fail closed to bound processing. The pre-existing distinction between partial months and complete 3-month windows remains unchanged.

Five synthetic regressions cover a year-boundary missing month, partial-edge completeness, canonical scorecard rejection, full coverage and unbounded windows.

## Scope and limitations

This is an **integrity improvement**, not a new strategy or replay. It does not fill absent minutes, change fixed $0.40/oz roundtrip costs, infer any monthly P/L, or certify M1 floating drawdown. Historical 2012–2025 data are exposed, not clean OOS. Shared-capacity portfolio and prospective validation remain pending.

- New original-source annual backtests: **0**
- New original-source monthly P/L: **N/A**
- New worst month / M1 floating drawdown: **N/A**
- Approved strategies: **0**
- PR #1 must remain **Draft** and unmerged.
- Private raw Gold BID/ASK ZIP must remain local.

CI verification is tracked by GitHub Actions on the final branch head, not inferred from a local synthetic check.
