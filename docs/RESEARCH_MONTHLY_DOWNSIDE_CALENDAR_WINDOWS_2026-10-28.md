# Monthly downside calendar-window audit — 2026-10-28

The read-only source-verified historical batch scorecard now reports the **longest consecutive nonpositive observed UTC month streak**, nonpositive months, months with trades, and the **worst three full consecutive UTC calendar months' net USD/oz** (including the $0.40/oz roundtrip fee already reconciled in the canonical trade/weekly/monthly ledgers). It also lists partial first/last requested calendar months.

The three-month downside result is **null / N/A** if no fully observed contiguous three-month calendar window exists. Partial requested months are not promoted to full-month evidence; missing months break consecutive streaks and cannot form a three-month window. Ties use the earliest window. A zero-trade month is nonpositive if its booked P/L is zero, not a positive-month success.

This is **exit-booked realized P/L**, not intrabar/M1 floating drawdown, a portfolio with shared capacity, or a forward/OOS certification. The scorecard only processes already executed and independently reconciled evidence; it never starts a backtest, changes fixed transaction fees, approves a strategy, or uploads private quotes. These are correlated parameter variants, not independent hypotheses.

Synthetic regression tests cover 2024 leap February, partial windows, gaps, zero-trade months, ties, malformed dates, duplicate months, nonfinite P/L and invalid trade counts. Keep PR #1 Draft. Exact-head CI and original private Gold source replay must be separately confirmed.
