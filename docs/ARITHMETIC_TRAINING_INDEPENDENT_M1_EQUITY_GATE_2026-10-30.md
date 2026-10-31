# Independent persisted M1 equity / floating-risk gate — 2026-10-30

## Scope
The arithmetic frozen-training dispatcher now independently audits the **persisted observed M1 close-equity ledger**, even when Reference and Fast agree. This is a *synthetic integrity gate*, not an original Gold-data strategy replay, clean OOS result, broker tick/fill authentication, or live authorization.

Implemented in `scripts/run_arithmetic_dispatch_training.py`; six adversarial tests in `tests/test_run_arithmetic_dispatch_training.py`.

## Checks
- Require observed `at`, `realized_pnl`, `floating_pnl`, `equity`, and `drawdown` fields; reject duplicate, unordered, timezone-naive, non-minute-aligned timestamps and coverage mismatches with `summary.json`.
- Require finite numeric marks and `realized_pnl + floating_pnl = equity` at every observed minute.
- Reconstruct running peak from **observed marks only**, anchored to initial zero research equity, and verify every per-mark drawdown and the annual summary maximum. No invented minutes or intrabar/tick-level claims.
- Independently reconcile exit-booked trade net P/L to the cumulative realized series on the **actual observed exit minute**; reject missing exit marks and out-of-range entries/exits.
- Verify summary last equity, last realized P/L, and observed training-month coverage; never accept identical Reference/Fast corruption as proof.
- Keep the already-audited fixed **$0.40/oz ALL-IN roundtrip**, UTC monthly/weekly exit booking, frozen training-only selection, and atomic no-partial-publication rules.

## Regression evidence
Six new identical-corruption negative controls: wrong observed drawdown, shifted realized timeline, duplicate minute, absent exit minute, forged annual drawdown summary, and forged last equity. Synthetic fixture spans all 12 UTC months without fabricating missing M1 minutes.

Executable commit: `a017a50e6b089a74d8d376d0b7cfeb901df21681`.
Full GitHub Actions **Engine quality gates**: https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41008069887 — **2,926 passed, 1 warning**, completed successfully.
GitHub Actions **Quant Lab causal formula regression**: https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41008076843 — success.

## Results and limits
New original-source XAUUSD strategy backtests: **0**. New original-source monthly P/L: **N/A**. New source-verified floating drawdown: **N/A**. Approved strategies: **0**. Existing FAC025 remains rejected at **6/24 positive months, -$234.602330/oz**, and must not be retuned.

The new M1 gate checks **persisted reference/fast evidence**, not independent price feed quality, actual bid/ask execution, true intraminute drawdown, or prospective embargoed OOS. The private `Gold data.zip` was not opened, uploaded, or replayed for this change. Draft PR #1 remains unmerged.
