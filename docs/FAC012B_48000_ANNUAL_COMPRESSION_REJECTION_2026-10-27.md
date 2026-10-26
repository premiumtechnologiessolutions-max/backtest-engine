# NRF-FAC-012B — 48,000 annual replays; no parameter passes frozen monthly gate (2026-10-27)

**FINAL DISPOSITION: REJECT all FAC012B variants on exposed 2012–2013 design history.** No clean OOS, broker-tick certification, live trade, or monthly-profit guarantee.

## Frozen chronology and negative feasibility control
- FAC012 first frozen [56e645c](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/56e645c8fb98a3cc2b00df775aa8c7328bea1626). Original requirement of 26 consecutive fully complete H1 bars proved infeasible (2012 maximum uninterrupted run **23**). **100 FAC012 annual replays, all zero-trade**, excluded from active totals; not silently counted as FAC012B.
- FAC012B gap-aware H1-only correction frozen **before FAC012B private results** at [bee2e7f](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/bee2e7f072b9a44a2592d007f2dd3fb7d41c23f7). Last 26 observed completed H1 candles within 168 elapsed hours, no fabricated bars. Prior24 observed H1 ranges within 168h; H1 close as-of M15 signal <=60min stale; H1 EMA8/24 alignment, pre-known H1 range-ratio halt and true DST-local sessions. See [frozen specification](FAC012B_FROZEN_GAP_AWARE_COMPRESSION_2026-10-27.md).
- **24,000 correlated specs/year**: 5 M15 breakout lookbacks × 4 previous-bar squeeze ratios × 2 H1 trend modes × 2 H1 volatility halts × 3 sessions × 10 prior-range-normalized SL × 10 prior-range-normalized TP. Not 24,000 independent hypotheses.
- Private original Gold ZIP SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` verified locally. Raw BID/ASK market quotes NEVER uploaded. Exactly **$0.40/oz ALL-IN roundtrip**, no extra spread; next eligible observed M1 open <=60s, stop-first, adverse opening gap-through, 1 position/yearly reset, exit-booked UTC months, M1 floating marked DD.

## Actually executed, original SHA-verified 2012/2013
| Metric | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Observed M1 | 352,975 | 352,317 | 705,292 |
| Fully complete M15 | 23,197 | 23,023 | 46,220 |
| Fully complete H1 | 5,600 | 5,486 | 11,086 |
| **Annual parameter-year replays** | **24,000** | **24,000** | **48,000** |
| Active annual replays (>=1 fill) | 24,000 | 24,000 | **48,000** |
| Monthly net P/L values | 288,000 | 288,000 | **576,000** |
| Distinct signal streams within year | 229 | 230 | correlated |
| Positive annual-net specs | 4,648 | 4,495 | **962 same IDs positive in both** |
| Maximum positive months | 11/12 | 12/12 | **20/24** |
| Specs 12/12 | 0 | 10 | **0/24,000 achieved 24/24** |

**32/24,000** achieved >=18/24 positive months; **0** passed the frozen combined gate: >=80 trades in each year, >=18/24 strictly positive months, net >0 each year, worst month >=-$20/oz and each annual observed M1 floating DD <=$100/oz. Among **8,902** variants with >=80 fills in both years, best month count was only **17/24**; only **122** also had positive net in both years, still <=17/24.

### Examples (exploratory, REJECT)
- **Highest positive months:** `COMP15_N12_Q1.15_ALIGNED_H1.20_NY_LOCAL_0930_1330_SL2.75_TP0.50`, **20/24**; +$13.155 in 2012 and +$15.66125 in 2013, **+$28.81625/oz** combined; only **16 and 38 fills**, $21.60 fees, worst month **-$11.82875**, annual M1 DD $5.81/$22.57625. **FAIL sample size**.
- **Highest net among >=80 fills in each year:** `COMP15_N08_Q0.75_CONTRA_H1.20_ALL_SL2.75_TP2.25`, **14/24**, **+$104.5925/oz** across separate years, 160/167 fills, $130.80 fees, worst month **-$18.91125**, max annual floating DD **$51.24375**. **FAIL monthly stability**.

Top 20/24 candidate Jan–Dec monthly net (USD/oz):
- **2012:** +3.055, +2.535, +0.890, 0, +2.230, 0, +1.3575, +0.8675, +1.1225, +0.6225, +0.475, 0 = **9/12** strictly positive.
- **2013:** +2.1375, +1.025, +2.2875, +1.445, +5.1275, +7.635, +2.015, +0.6075, -11.82875, +2.915, +1.5025, +0.7925 = **11/12**.

## Validation boundary
All 48,000 actual original-source M1 annual replays were executed locally. All 576,000 monthly net cells reconcile to annual net, fees to $0.40 × fills. **10 full-year deterministic samples (5/year)** matched an independently written local Python per-M1 reference on monthly nets, trades, fees, net and M1 floating DD (maximum DD difference 7.11e-15). **These 10 are independent slow-reference samples, NOT certified official full-repository canonical source-data parity**. GitHub script includes canonical `run_fast` sample checks for a future official private-source replay; public GitHub Actions can only run synthetic tests. Do not claim source-data canonical parity from CI alone.

Full monthly ledgers are retained in private local research bundle without raw quotes. No shared-capacity multi-strategy portfolio was executed; never add stand-alone profits. 2012–2016 previously exposed; no clean OOS, severe selection bias. Forward embargoed prospective testing and independent tick/spread source remain necessary.
