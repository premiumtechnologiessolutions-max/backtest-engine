# Single-position entry-delay and signal-side validation — 2026-10-26

## Issue found on branch head 9f8ee15

`Settings(max_entry_delay_minutes=float("nan"))` previously passed `if delay < 0`. NaN compares false to zero and also makes stale-signal comparisons false, potentially retaining obsolete signals indefinitely. Positive infinity and positive fractional values likewise passed. The multi-strategy `PortfolioSettings` already rejects these values.

`Signal(..., side=True, ...)` also passed `side in (1, -1)` because Python treats `True == 1`. Float sides `1.0` and `-1.0` were accepted as well, weakening the discrete +1/-1 ledger contract.

## Changes

- `Settings.max_entry_delay_minutes` now requires a non-boolean integral value >= 0. Defaults and valid integer values are unchanged; both reference and fast execution use this setting.
- `Signal.side` now requires a non-boolean integral value exactly +1 or -1. No trading signal generation or execution prices were modified.
- Added parameterized regression cases for NaN, positive/negative infinity, fractional and boolean delays; boolean, float, NaN and string trade sides; and valid integer controls.

## Verification boundaries

- 19/19 **isolated local** checks passed against a copied model module with the same validation conditions (Python + pytest). These are NOT the repository-wide tests.
- New regression tests have been committed to `tests/test_subsecond_causality_and_quote_guards.py`, but the full repository pytest, installed wheel/sdist suite, original ZIP 13-field replay and GitHub Actions have NOT been executed on this head.
- No raw market data, fees, strategy thresholds or historical trade results changed. Keep Draft PR #1 unmerged until acceptance gates are independently verified.
