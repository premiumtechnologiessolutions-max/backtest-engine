# Arithmetic training replay — independent monthly exit-booking gate (2026-10-30)

**Status: code and six synthetic regressions committed; full-head CI pending.**
This change strengthens `scripts/run_arithmetic_dispatch_training.py` after the frozen Reference/Fast comparison. A pair of matching monthly reports can still be wrong if both engines place P/L into the wrong calendar month. Matching annual net P/L is not sufficient for the project's monthly-stability objective.

## New independent checks

- Require exactly 12 **ordered, unique UTC YYYY-MM** rows for the selected exposed training year; missing zero-trade months are not silently omitted.
- Reconstruct each month's `trades`, `wins`, `net_pnl`, and `total_cost` from each persisted fill's **actual UTC exit timestamp**, and reject nonfinite/non-numeric fields, negative/fractional counts, or summary positive-month mismatch.
- Reject exits booked outside the requested training year. Existing Reference/Fast 15-field trade and observed M1-equity parity, per-trade exactly **$0.40/oz ALL-IN** and atomic publication checks remain mandatory.
- Six synthetic negative tests independently corrupt *both* engines in the same way (offsetting P/L transfers, missing/duplicated months, wrong fees, trade counts or wins). They must all fail without publishing a partial batch.

**This is an integrity improvement, not a new hypothesis or a new original-source backtest.** No monthly P/L or floating drawdown is newly measured; both remain **N/A**. FAC025 remains REJECT (6/24 positive months, -$234.602330/oz historical BID proxy), with zero approved strategies. The runner still requires private source SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`, and cannot claim authenticated broker BID/ASK fills, tick-level DD, prospective embargoed OOS or trading readiness.

To verify after checkout: `python -m pytest -q tests/test_run_arithmetic_dispatch_training.py`, then full Engine quality gates on the exact code commit. Keep PR #1 Draft/unmerged; never upload private Gold ZIP.
