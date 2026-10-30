# Historical candidate-screen monthly downside and inactivity — 2026-10-30

This update adds **descriptive training-only calendar risk diagnostics** to the existing source-audited candidate screen. The frozen batch manifest, each monthly ledger SHA256, complete calendar coverage, and training/review isolation remain mandatory. An incomplete search universe cannot receive rank or promotion labels.

For each contiguous UTC monthly window, show: (1) worst net month, (2) worst rolling three-month **net** USD/oz sum, (3) zero-trade month count, (4) longest consecutive nonpositive month streak, with zero treated as nonpositive. Display these next to number of trades, profitable months and **month-end** drawdown. A zero-trade month is never counted as profitable. The rolling-three metric requires at least three observed calendar months. None of these quantities is observed M1 floating drawdown or an intraminute risk estimate.

Synthetic tests cover negative/flat months, inactivity, streaks, rendering, nonfinite and missing monthly data. Existing review-isolation tests continue to ensure later-period changes cannot influence training ranking. These diagnostics do not alter trade execution, strategy selection, fees, or search-multiplicity controls.

**Backtests newly executed: 0.** Original Gold ZIP newly replayed: **no**. Newly verified monthly P/L: **N/A**; floating M1 drawdown: **N/A**; independent OOS: **not proven**; approved strategies: **0**. Existing $0.40/oz all-in cost is already reflected in the audited net source. This is not a new independent trading hypothesis. Keep Draft PR #1 unmerged and private raw quotes out of the public repository.
