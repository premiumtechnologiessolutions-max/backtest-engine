# FAC022 — independent offline CSV arithmetic reconciliation (2026-10-27)

**Scope:** Read-only audit of the existing user-supplied `NoRiskFX_FAC022_4608_Annual_M1_Research_2026-10-27.zip`. This is **not a new backtest**, **not an independent canonical replay**, and **not clean out-of-sample evidence**. No raw quotes or trade ledgers were uploaded.

The private original `Gold data.zip` was separately materialized locally and its SHA256 matched `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`; this CSV audit itself does not load market data.

## Verified exported arithmetic

- Exactly **2,304 distinct correlated parameter IDs** in both 2012 and 2013 annual exports and the combined file. These are **one logical family**, not 2,304 independent hypotheses.
- Reconciled **4,608 annual rows** and **55,296 monthly booked-P/L cells**. No duplicate or missing parameter IDs.
- Every annual net equals the sum of its 12 calendar-month values (maximum absolute discrepancy under `5.2e-11`); each annual fee equals **$0.40/oz × filled trades** (maximum discrepancy under `4.1e-11`).
- All 2,304 combined IDs reconcile yearly trade counts, monthly positive counts, worst month, combined fees, combined net and maximum of the two reported annual floating drawdowns (maximum combined-file absolute discrepancy under `4.6e-13`). **Floating drawdown values were checked for internal consistency only, not reconstructed from M1.**
- **Maximum 15/24 profitable months**. **Zero** candidates positive in both calendar years; in fact **every candidate's combined 2012+2013 net is negative**, with the *least negative* combined net **-$20.20/oz** after reported costs.
- All **2,304** frozen joint acceptance flags reconcile; **0 passes**. The highest-month-count candidate is **not** the least-loss candidate. The family remains **REJECT**.

## Verification boundary

An independent local pandas/CSV audit compared the two annual CSVs against the combined CSV by exact parameter ID; it checked all monthly values, fees, net, worst month, reported drawdown, positive-month counts and frozen gate. This arithmetic-only check does not prove signal causality, order execution, M1 equity, source authenticity, independent OOS or broker spreads. The original canonical replay and parity evidence remain in the existing FAC022 report.

**Acceptance:** No change to historical bulk totals, no refitting of rejected families, no new backtests or forward validation. Keep PR #1 Draft and unmerged. CI on this document commit must be checked separately; never label a pending workflow successful.
