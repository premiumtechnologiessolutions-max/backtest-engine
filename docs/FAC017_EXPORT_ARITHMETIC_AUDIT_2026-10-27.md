# FAC017 local CSV independent arithmetic audit — 2026-10-27

**Scope: audit existing FAC017 local export; no new XAUUSD market-data replay.** This audit independently parses the existing 2012 and 2013 annual candidate CSVs and combined CSV from the conversation archive NoRiskFX_FAC017_LOCAL_36864_Annual_M1_Research_2026-10-27.zip. It does **not** establish that the locally ported strategy/execution matches the full official run_fast or canonical reference engine. The original Gold ZIP was not available for an independent source replay in this run.

Run the new scripts/audit_fac017_local_exports.py with --year-2012, --year-2013, --combined pointing at the three extracted CSVs. Do not upload original BID/ASK/M1, private ZIP, or detailed ledgers to this public repository.

## Observed, locally rechecked CSV arithmetic

- Frozen parameter IDs: 18,432 unique IDs in **each** of two years; exactly the preregistered 4×4×3×2×3×8×8 grid, not 18,432 independent hypotheses.
- 36,864 **previously completed local** annual replays, of which 34,624 active and 2,240 zero-trade. **No new replays** were executed by this audit. 442,368 annual-row monthly cells including zero-trade rows.
- All annual monthly sums reconcile to annual net within 1e-7; all fees reconcile to exactly $0.40 × fills, with no separate spread deduction; positive-month counts, worst-month, combined annual fields, max annual floating DD and preregistered gate recompute consistently.
- 2012 active 16,896, zero-trade 1,536; 2013 active 17,728, zero-trade 704.
- Max 20/24 strictly profitable months. **Five** correlated configurations had >=18/24 profitable months (three at 18, one at 19, one at 20); **none** passed the frozen joint acceptance screen. Zero at 24/24. 1,080 were net positive in both years but this is insufficient for acceptance.
- **15,872/18,432** failed the >=100 fills **in each** year gate; **18,427/18,432** failed the >=18/24 months gate; 17,352 failed positive net in both years; 2,516 failed worst month >=-$20; 1,298 failed max annual floating DD <=$100. These counts overlap and are not independent failure categories.
- The combined export field fills_both denotes **>=100 fills in each year**, not merely nonzero fills in both years. This distinction is now explicitly checked.
- Maximum absolute annual monthly-net reconciliation residual was below 1.8e-12; max fee residual below 1.4e-12; combined metrics were within 1e-7. These are **internal arithmetic checks only**, not independent M1 quote/ledger or strategy parity.

## Remaining gates

1. Locate the original private ZIP, verify its exact SHA256 1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121 **locally**, and rerun the **official GitHub checkout** FAC017 runner against it without modifying frozen parameters.
2. Reconcile official run_fast vs canonical reference full trade ledger, fees, next-open timing, stop-first, adverse gap-through and every observed M1 floating equity mark for preregistered samples. Do not certify or increment factory totals before this gate.
3. Maintain historical exposure warning for 2012–2016. Prospective OOS with embargo and multiple-testing controls is still unperformed; no shared-capacity portfolio has been validated for FAC017.

Keep PR #1 Draft/unmerged, no live trading, no billing/privacy changes. This arithmetic audit is useful negative-result verification, **not** evidence of monthly profit or a new independent hypothesis.
