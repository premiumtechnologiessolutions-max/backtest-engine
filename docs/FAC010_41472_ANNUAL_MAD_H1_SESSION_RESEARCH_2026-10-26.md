# NRF-FAC-010 — original-source robust-MAD/H1/session design batch (2026-10-26)

**REJECT all configurations by the frozen screening gate.** This is historically exposed **2012–2013 DESIGN research**, not independent OOS, not a monthly-profit or live-fill claim. The preregistration was committed first at [042b061](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/042b0619c0c9ab510a22a7770794b1d0d1117517), **before** the first FAC010 outcomes were inspected. Frozen contract: [FAC010_FROZEN_MAD_H1_SESSION_2026-10-26.md](FAC010_FROZEN_MAD_H1_SESSION_2026-10-26.md).

## Actual executed scope, not hypothetical generators

Original private `Gold data.zip` SHA256 **1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121**, independently checked locally; no raw BID/ASK quotes committed or sent to Actions. The fixed cost is **exactly $0.40/oz ALL-IN roundtrip only**, 1 oz, one slot, BID-reference OHLC, stop-first and adverse opening gap-through. All month results are exit-booked UTC; M1 floating drawdown includes open-position marks and the fixed fee.

| Measured metric | 2012 | 2013 | Joint |
|---|---:|---:|---:|
| Original M1 observations | 352,975 | 352,317 | 705,292 |
| Complete M15 / H1 bars | 23,197 / 5,600 | 23,023 / 5,486 | — |
| **Executed annual parameter backtests** | **20,736** | **20,736** | **41,472** |
| Exit-booked monthly P/L values | 248,832 | 248,832 | **497,664** |
| Distinct entry signal sequences | 144 | 144 | Not 288 independent hypotheses |
| Zero-trade specifications | 0 | 0 | 0 |
| Positive annual net specifications | 896 | 1,436 | **343 exact IDs positive in both years** |
| Configurations with all 12 months positive | 2 | 2 | **0 exact IDs 24/24** |

**Maximum observed positive months for any exact 2012+2013 specification: 21/24.** 41 parameter IDs scored >=18/24, 18 of them net-positive in both years. **0/20,736** passed the fully frozen gate (>=18/24, net-positive each year, >=50 trades per year, worst month >= -$20/oz, M1 DD <=$100/oz per year).

### Highest month-count configuration: REJECT
`MAD15_W48_Z1.75_QUIET085_EU_FIXED_UTC_SL6.00_TP0.50`: **21/24** positive months, but **2012 net -$9.80** (32 trades), 2013 net **+$3.70** (37 trades), **joint -$6.10/oz**, worst month **-$6.30**, M1 DD 2012 **$15.68**, 2013 **$6.25**. Total fixed fees **$27.60** across separately reset years. It fails the annual net and minimum sample-size gates. No posthoc modification.

2012 Jan–Dec net USD/oz: `+0.20,+0.30,+0.70,+0.10,+0.40,+0.10,-6.30,-5.90,+0.20,0.00,+0.20,+0.20`.

2013 Jan–Dec net USD/oz: `+0.20,+0.30,+0.30,+0.40,+0.20,+0.10,+0.30,+0.20,+0.30,+0.50,+0.40,+0.50`.

### Highest month-count configuration also annual-positive both years: still REJECT
`MAD15_W48_Z1.75_QUIET085_EU_FIXED_UTC_SL4.00_TP5.00`: **20/24** positive months; 2012 **+$34.60**, 2013 **+$39.60**, joint **+$74.20/oz**. Only **31 and 36 trades/year** versus preregistered >=50 each. Worst month **-$4.40**; annual M1 DD **$16.61** and **$12.69**. Exact total fixed fees **$26.80**. These are selected posthoc among 20,736 correlated parameterizations; **not a validated candidate**.

2012 Jan–Dec net USD/oz: `+0.20,+4.80,+9.60,+4.60,+0.40,-4.40,+0.20,+0.60,+0.20,0.00,+9.20,+9.20`.

2013 Jan–Dec net USD/oz: `+0.20,+4.80,-4.20,+0.40,+0.20,+4.60,+4.80,+0.20,-4.20,+9.40,+18.40,+5.00`.

## Reproducibility and verification scope

- Local private archive authenticated by SHA256. The accelerated replay executed every frozen parameter ID in both years. Full 12-month candidate matrices, exact parameter IDs, net, fees, trades, worst month, M1 floating DD and signal counts are retained in a private FAC010 results bundle; **the 41,472 rows are not public raw quotes**.
- **6 deterministic original-source parity samples** (3/year) matched a local copy of the repository `fast_engine.run_fast` implementation at commit `ee605226` for all 12 monthly nets, total fees, executed count, total net and floating M1 DD within 1e-7. The six samples independently matched a separate slow per-M1 replay, too. A locally reconstructed import environment executed the GitHub-target script and reproduced **all 20,736 annual candidate rows per year exactly**. This is strong local verification, but the actual GitHub checkout/official full package has **not** yet been executed on private data in this run.
- Public synthetic contract regression tests are committed in `tests/test_batch_mad_h1_session_grid.py`; **latest-commit GitHub Actions status remains unverified as of report publication**. Earlier CI (661 tests at `ee605226`) must not be attributed to this new head.
- No jointly capacity-constrained FAC010 portfolio was evaluated; never add standalone winners and label the sum a portfolio. No independent tick-spread execution, no funded margin model, no clean prospective holdout. 2012–2016 previously exposed.

**Disposition:** freeze FAC010 as a negative design batch, keep its complete negative search history. Next: independent prospective collection with embargo, family-level multiple-testing control and a separately frozen shared-capacity portfolio; do not retune the rejected FAC007 candidate. PR remains Draft and unmerged.
