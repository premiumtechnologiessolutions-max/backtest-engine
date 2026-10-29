# Complete-month downside and trade-support integrity — 2026-10-30

## Risk-reporting change

The audited canonical monthly scorecard now distinguishes **complete UTC calendar months** from partially observed first/last months. It publishes `complete_calendar_months_observed`, `complete_nonpositive_calendar_months`, `longest_nonpositive_complete_calendar_month_streak`, and the worst **complete** month's UTC label and net USD/oz. Partial months remain in the existing observed-month loss streak and the existing worst observed month, but cannot masquerade as complete-month risk evidence.

For the worst three consecutive **complete** UTC calendar months, the scorecard now also publishes `worst_three_complete_calendar_months_trade_count`. This is the actual sum of canonical monthly trade counts, **not** three independent strategy trials, not proof of statistical power, and not a portfolio capacity audit. The field is null when no eligible three-month window exists. Earliest UTC window/month wins tied worst-net values. Missing calendar months still cause the parent scorecard to reject the run.

## Verification and limits

Four new synthetic tests cover partial-edge exclusions, trade support, missing-month streak breaks, and earliest-month ties. Exact-code GitHub CI must pass before treating this as verified. No original BID/ASK backtest, no monthly profits, no floating M1 drawdown, no new strategy, and no prospective OOS were produced by this change. The all-in roundtrip fee remains exactly **$0.40/oz**; source data stay private. PR #1 remains Draft/unmerged.
