# XAUUSD direct ZIP multi-year completeness gate — 2026-10-26

## Finding
Before this change, `load_market(source_zip, start, end)` could return a partial
multi-year M1 sample when the archive had at least one requested annual JSON
member but omitted another requested year. The returned DataFrame did not
declare which annual members were missing. This is a data-coverage integrity
issue: a backtest could be interpreted as covering all selected years when it
did not.

## Change
The direct ZIP loader now enumerates requested calendar years using the
existing **exclusive upper bound** (`last_included_year`) and fails closed if
any requested annual member is missing **and at least one requested member
exists**. If no requested members exist, the previous no-source error remains.
An unrequested following year is never required. Duplicate annual members
continue to be rejected.

This gate checks annual *member presence*, not complete minute coverage
inside the member, official exchange holidays, quote authenticity, or
broker/tick execution. It does not fill or fabricate any missing M1 bars.

## Regression coverage added
- Multi-year 2024–2026 ZIP containing 2024 and 2026 but missing 2025 must
  raise `Missing requested ZIP source years: [2025]`.
- A 2024-only ZIP queried through 2024-12-31 must succeed without 2025.

These regression cases are **committed but have not been executed** under the
full current GitHub repository test environment. They are not evidence of
historical 13-field parity, full `pytest`, or successful GitHub Actions.

## Research controls unchanged
Original Gold archive SHA-256 remains
`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
The fixed ALL-IN fee remains $0.40/oz. No strategy logic, trade results, raw
quotes, private archive, or claimed OOS designation were changed.

PR #1 stays Draft until full current-HEAD `pytest`, actual original-source
13-field ledger parity, and a successful CI run can be demonstrated.
