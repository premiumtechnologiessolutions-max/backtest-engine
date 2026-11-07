# Quant Lab — fail-closed worker progress acknowledgement (2026-10-29)

## Observed CI regression
On exact head `d2f6951f0e19b7d9c66e1451ab58742d8d3ec825`, GitHub Actions run 40952737209 failed 1 of 2,719 tests (2,718 passed). The failing synthetic recovery test mocked `run_plan` with `None`, while the production worker dereferenced `.get()` and correctly did not clear its error. The mock was not a valid successful runner response.

## Change
Both the single-batch worker and bounded autopilot now require a real dictionary acknowledgement with an exact non-boolean integer `executed_this_invocation` between zero and the operator's requested batch budget. Autopilot additionally rejects missing, boolean, negative, inverted, or over-cap `reconciled_jobs` and `defined_jobs`. A malformed response records an explicit ValueError; no progress is credited and the worker returns to IDLE. Recovery tests now use a structurally valid mocked response. Added 12 negative synthetic cases (6 per worker), plus the corrected recovery fixture.

## Scientific limitations
These are synthetic application control tests, **not** original-source XAUUSD BID/ASK backtests, certified monthly P/L, floating M1 drawdown, or OOS. The original source remains private. Historical factory totals, $0.40/oz ALL-IN fee, strategy hypotheses, and frozen grids are unchanged. The PR must remain Draft and unmerged; this document does not claim CI success before an exact-head successful run.
