# Monthly exit-ledger accounting integrity gate — 2026-10-30

The exploratory historical candidate screen now rejects **nonzero exit-booked monthly net P/L when the same UTC month has zero completed trades**. This is a consistency gate on *realized, exit-booked* monthly evidence, not on mark-to-market equity: a month with an open position and zero exits can have floating exposure, but must not report realized trade P/L from that position.

The risk arithmetic also rejects finite monthly values that would overflow cumulative equity, peak-to-trough drawdown, total net P/L, or contiguous three-month net P/L. Total and rolling sums use `math.fsum` for more stable floating-point aggregation. These are fail-closed guards; they neither improve a strategy nor alter the $0.40/oz ALL-IN roundtrip fee or trade execution.

Synthetic tests: `tests/test_research_candidate_screen_accounting_integrity.py` covers impossible positive/negative P/L in a zero-trade month, legitimate flat inactivity, overflowed cumulative equity, overflowed monthly aggregation, and overflowed peak-to-trough drawdown. Existing source-verified manifest and SHA-pinned monthly ledger gates remain mandatory. The candidate screen is still **historically exposed, descriptive and not independently OOS validated**; the reported drawdown is month-end only, not observed floating M1 drawdown.

**New original Gold backtests: 0; new source-verified monthly results: N/A; new M1 floating drawdown: N/A; independently approved strategies: 0.** No raw Gold data, private quotes, trade ledger or equity traces are included in this public repository. Keep PR #1 Draft and unmerged. Verify exact-head GitHub CI after code, test, documentation and registry updates; do not reuse an earlier commit's CI claim.
