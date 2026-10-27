# Walk-forward UTC and embargo contract — 2026-10-27

## Why this gate exists

A hand-constructed `WalkForwardFold` previously accepted a declared seven-day embargo even if training ended only one day before evaluation. That made the fold metadata falsely imply a purge window that was never reserved. The fold also accepted non-UTC timezones, while `require_training_only` and `purge_cross_boundary_trades` silently localized timezone-naive trade timestamps as UTC. Missing exit timestamps could be silently filtered instead of reported as invalid.

These are research-integrity issues: a time-based backtest must never silently invent timestamp provenance or certify an embargo that does not exist.

## Changes

- Require finite UTC-aware fold boundaries; reject non-UTC timezone offsets.
- Require an actual train-end to evaluation-start gap of at least `embargo_days` calendar days, with nonnegative integer embargo metadata.
- Reject boolean or fractional year-fold arguments instead of interpreting them as valid integers.
- Require explicitly UTC-aware, nonmissing trade entry/close times before training selection or position purging. Do not call `pd.to_datetime(..., utc=True)` on naive inputs.
- Preserve empty trade tables and existing valid UTC fold behavior.
- Add 13 focused regression cases for false embargo, non-UTC boundaries, naive/missing trade dates, and invalid integer parameters.

## Evidence and limitations

Source: `src/norisk_quant/walkforward.py`; tests: `tests/test_walkforward.py`. The tests use **synthetic timestamps only**. The final GitHub Actions run must pass on the exact final commit before declaring this change CI-verified. No original market ZIP, archived reference ledger, broker tick data, or research OOS results are included or uploaded.

This gate prevents certain false time-split claims but does **not** establish that evaluation data were genuinely unseen, that open positions were independently audited at the boundary, or that any trading strategy is profitable. Keep PR #1 Draft until the full acceptance criteria are met.
