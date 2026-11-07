# FAC020 — 24,576 annual M1 replays, lagged variance-ratio M15: REJECT (2026-10-27)

**Status: COMPLETED / EXPOSED DESIGN / REJECT.** Frozen hypothesis and 12,288-spec grid **before any FAC020 results** at commit `ba44ef7ce25319df19389e7d2933d5df5d117236`; see [preregistration](FAC020_FROZEN_LAGGED_VARIANCE_RATIO_M15_2026-10-27.md). This is **one** new hypothesis family with 12,288 correlated parameter specifications, NOT 12,288 independent hypotheses. No clean OOS or broker-tick evidence. No strategy passed the frozen joint acceptance screen; do not retune these exposed years.

## Signal-only feasibility, before exit P/L

Original private `Gold data.zip` SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` verified locally; original raw BID/ASK never uploaded. **192 distinct causal entry-rule IDs/year**, all 192 generated nonzero signals. 2012 maximum 3,099 signals; 2013 maximum 3,166. **163 same IDs** generated at least 100 signals in BOTH years, so the frozen minimum-fill requirement was *not structurally impossible* and full M1 exit grid was justified. Signal count is an upper bound on fills, not evidence of filled trades.

## Completed original-source grid and frozen screen

| Metric | Result |
|---|---:|
| Frozen parameter specs per year | 12,288 |
| Actually executed annual M1 replays, 2012+2013 | **24,576** |
| Active replays with >=1 filled trade | **24,576** |
| Zero-trade annual replays | **0** |
| Exit-booked monthly net P/L values | **294,912** |
| Highest positive UTC months for a SAME-ID configuration | **19/24** |
| Configurations with >=18/24 positive months | **4/12,288** |
| Configurations with 24/24 | **0** |
| Configurations with positive annual net in BOTH years | **111** |
| Configurations passing ALL frozen acceptance conditions | **0** |

**Highest positive-month count (exploratory only, NOT approved):**
`VR20_N08_REVERT_V0.95_B0.50_CALM_NY_LOCAL_0930_1330_SL1.50_TP1.50`.

2012: **10/12** positive months, **80 fills**, **+$93.355/oz** after **$32.00** all-in fees, worst UTC month **-$2.845**, maximum observed annual M1 floating DD **$11.2325**. 2013: **9/12**, **101 fills**, **+$14.800/oz** after **$40.40** fees, worst month **-$11.6575**, M1 floating DD **$27.325**. Combined **19/24**, **181 fills**, **+$108.155/oz after $72.40 fees**, worst month **-$11.6575**, max annual floating DD **$27.325**. **REJECT**: 2012 has only 80 fills, below the preregistered **100 per year**; do not lower the threshold. The largest total-net setting is a different configuration with only 16/24 positive months; do not substitute it to claim acceptance.

**All 24 UTC exit-booked net monthly values ($/oz), exploratory same-ID only:**

| UTC month | 2012 | 2013 |
|---|---:|---:|
| Jan | +6.2975 | -11.6575 |
| Feb | +21.1325 | +5.7850 |
| Mar | +7.6025 | +6.3400 |
| Apr | +7.3525 | +4.4200 |
| May | +9.3225 | +8.5475 |
| Jun | +22.1350 | +6.7300 |
| Jul | -1.2075 | -8.2725 |
| Aug | +11.3500 | +3.7475 |
| Sep | +0.0825 | +0.7600 |
| Oct | +5.5675 | -5.6425 |
| Nov | -2.8450 | +2.5550 |
| Dec | +6.5650 | +1.4875 |

## Reproducibility, canonical and independent slow reference

**Exact verified source:** GitHub Actions run [40503150804](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40503150804), commit `3f28fa2f93a2bc641dd646ba21f4ef7b29289d99`, **1,073/1,073 tests passed**, Python 3.12.15; verified-source artifact ID `12733098945`, ZIP SHA256 `3d5af6c9491b0236b53537c1fc2b03269c2537ff7d8f44e046ead2e8b47a45c7`. Artifact source was downloaded and run **locally against original SHA-verified private ZIP**, using Python 3.13.5 locally (different from CI). Both 12,288-row/year official-source annual grids reproduced all **24,576 annual rows and 294,912 monthly values**, **zero numeric difference** across 22 numeric columns and identical parameter IDs.

**8 canonical `run_fast` annual parity samples** (4 per year) matched monthly P/L, fees, filled trade count and observed floating M1 DD exactly. In addition, an **independent `execution.run` vs `run_fast` slow full-year check** on the exploratory 19/24 setting verified **181/181 filled trades**, **all 15 trade fields**, and **705,292/705,292 observed M1 equity marks**, exact equality (2012: 80 fills/352,975 marks; 2013: 101 fills/352,317 marks). These checks certify this historical OHLC replay consistency only; not tick-level execution or broker profitability.

The one-position restriction is applied **within each candidate annual replay**. No merged cross-strategy portfolio was tested or accepted in FAC020; **do not sum different candidate profits as a shared-capacity portfolio**. No forward/prospective data with embargo or multiple-testing controls is available. All 2012–2016 history is exposed. Factory counts increase **only** by actually executed 24,576 active annual replays and 294,912 active monthly values; preflight-only runs are not counted as backtests. Keep PR #1 **Draft and unmerged**; no billing/privacy changes or live trading.
