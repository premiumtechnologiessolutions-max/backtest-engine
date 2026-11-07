# FAC025 monthly M1 equity strict numeric evidence gate — 2026-10-29

## Evidence-integrity defect and repair

The monthly observed-M1 drawdown helper previously called `to_numpy(dtype=float)` on three equity fields without checking their original column dtypes. Consequently a string column such as `["0", "-1"]` or boolean evidence could be silently converted to numbers, and a complex column could be lossy-cast. A duplicate `equity` column label could also make the selected matrix ambiguous. These are not acceptable as canonical-equity evidence.

The helper now fails closed if any column label is duplicated or if `equity`, `realized_pnl`, or `floating_pnl` lacks a real integer/float dtype. Existing exact M1 timestamp parity, minute alignment, finite checks, realized+floating reconciliation and monthly drawdown calculations are unchanged. This check does **not** assert authenticated market quotes, complete sessions, tick execution or prospective OOS.

## Verification and scope

Six synthetic regressions exercise numeric-text, booleans, complex numbers, mixed-object data, duplicate columns, and a valid mixed integer/float example. Local isolated pytest: **6 passed**. Full GitHub CI must be verified on the resulting exact commit; local tests alone do not certify the complete suite.

No new original Gold ZIP strategy backtests, monthly returns, or floating-risk results were computed: **N/A**. No change to frozen FAC025's 72 correlated filter specs (one hypothesis), execution rules, shared capacity, or exactly **$0.40/oz ALL-IN roundtrip**. Original M1 BID/ASK data must remain private. PR #1 stays Draft and unmerged.
