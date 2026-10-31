# NRF-FAC-011 — 38,400 annual replays and locked 2014–2016 rejection (2026-10-26)

**FINAL RESEARCH DISPOSITION: REJECT the sole preregistered-screen candidate after locked chronological stress.** Historical 2012–2016 are exposed and NOT clean independent out-of-sample. No broker tick execution or future monthly-profit claim.

## Precommit evidence and source integrity

- FAC011 entry/grid frozen at [commit 4dc1118](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/4dc11184bc6118aab8e97450bc0c0c884cd23d85), **before** the 2012–2013 FAC011 outcomes were inspected: [frozen hypothesis](FAC011_FROZEN_DIRECTIONAL_RUN_H1_LOCAL_SESSIONS_2026-10-26.md).
- After the entire 2012–2013 screen, the sole qualifying candidate was locked for 2014–2016 at [commit 34bec24](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/34bec248970622dce568e5e7fe95cde4a6ad2bb5), **before** this candidate's 2014–2016 replay: [locked specification](FAC011_LOCKED_CHRONOLOGY_2026-10-26.md).
- Original private `Gold data.zip` SHA256 **1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121**, checked locally. Raw BID/ASK quotes were **not** uploaded to public GitHub/Actions.
- Causal M15 *exact N-run* move / prior32 median M15 ranges, last completed H1 regime / prior24 observed H1 ranges, DST-aware London and New York local sessions, gap-separated baselines. Single 1-oz position per annual replay, next observed M1 open <=60s, stop-first, adverse opening gap-through, exactly **$0.40/oz ALL-IN roundtrip only**. Exit-booked UTC calendar months; M1 floating DD includes fee and open positions. No fabricated M1.

## Executed bulk grid (not a hypothetical generator)

| Metric | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Actual M1 observations | 352,975 | 352,317 | 705,292 |
| **Executed annual parameter replays** | **19,200** | **19,200** | **38,400** |
| Annual replays with >=1 filled trade | 18,800 | 19,000 | **37,800** |
| Zero-trade annual negative controls | 400 | 200 | **600** |
| Exit-booked monthly net values (including zero-trade rows) | 230,400 | 230,400 | **460,800** |
| Unique entry signal sequences (after deduplication) | 189 | 191 | correlated |
| Parameter specs with annual net >0 | 3,545 | 3,332 | **918 exact IDs >0 both years** |
| All 12 months positive | 12 | 2 | **0 exact IDs 24/24** |

- **19,200 distinct correlated parameter specs**, not 19,200 independent trading hypotheses. 18,600 exact IDs generated filled trades in BOTH years. The 600 zero-trade yearly executions are excluded from meaningful active-backtest totals.
- Highest monthly stability: **23/24**, achieved by `RUN15_N2_K3.00_FADE_HOT_LONDON_LOCAL_08_12_SL10.00_TP0.50`. Net 2012 **+$3.70**, 2013 **+$3.40**, only **37 and 34 trades**, worst month $0 (zero trade is NOT positive), annual max M1 DD <=$9.28. **REJECT** due to insufficient sample size (<80/year). Posthoc selection among correlated variants; not validated.
- **352** specs reached >=18/24 positive months. Exactly **ONE** passed ALL preregistered descriptive gates (>=18/24, positive net each year, >=80 fills/year, worst month >=-$20, annual M1 floating DD <=$100).
- That single screen pass, `RUN15_N3_K3.00_FOLLOW_HOT_ALL_SL3.00_TP6.00`, had **18/24 positive months**, 2012 **+$73.14 / 222 trades / $88.80 fees / $50.99 DD**, 2013 **+$52.00 / 170 trades / $68.00 fees / $48.05 DD**, worst month **-$10.60**. This was only a descriptive historical screen, NOT proof of a robust edge.

### Sole screened candidate: all 24 design-month nets (USD/oz)

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2012 | +9.80 | -5.00 | -1.80 | +0.60 | +6.20 | +1.80 | +18.80 | +15.20 | -7.20 | +0.74 | +24.40 | +9.60 |
| 2013 | +8.80 | +7.40 | +2.00 | +15.40 | +6.40 | +23.20 | +7.40 | +2.00 | -2.60 | -10.60 | -10.40 | +3.00 |

## Locked, unchanged 2014–2016 chronology stress: FAIL

Frozen continuation gate: >=27/36 positive months, net positive **each** year, >=80 trades/year, worst month >=-$20, M1 floating DD <=$100 each year. **No parameter modification** after design screening.

| Metric | 2014 | 2015 | 2016 | Combined (separate annual resets) |
|---|---:|---:|---:|---:|
| Filled trades | 189 | 208 | 172 | **569** |
| Positive months | 4/12 | 3/12 | 3/12 | **10/36** |
| Net after fixed fees USD/oz | **-$124.20** | **-$98.70** | **-$98.80** | **-$321.70** |
| Total fees USD/oz | $75.60 | $83.20 | $68.80 | **$227.60** |
| Worst month USD/oz | -$27.60 | -$30.62 | -$30.80 | **-$30.80** |
| Annual M1 floating DD USD/oz | $134.85 | $139.26 | $107.76 | **max $139.26** |

Locked monthly P/L, Jan–Dec:
- **2014:** +0.80, -10.40, -8.20, -22.80, +7.60, +11.98, -27.60, -20.80, +3.00, -18.78, -11.40, -27.60.
- **2015:** -17.40, -24.00, -7.20, -12.80, -15.00, -30.62, -25.20, +18.80, -12.80, -0.60, +4.20, +23.92.
- **2016:** -11.40, -15.00, -1.60, -30.80, +4.20, -13.80, +6.40, +19.80, -16.20, -12.80, -10.40, -17.20.

**REJECT** locked candidate, do not retune it using these historical years. The 2014–2016 chronology is a stress test on already historically exposed data, NOT clean OOS. No shared-capacity portfolio was simulated, so no combined-portfolio P/L is claimed.

## Verification boundaries and follow-up

- Local original-source Numba event replay completed all 38,400 parameter-year runs; monthly sums reconciled to annual net and every filled trade to exactly $0.40 fee. 2012/2013: **8 deterministic annual parameter samples** matched a separately written **local slow per-M1 reference** on 12 monthly nets, trades, fees, net and floating DD (zero differences). 2014–2016: **3 complete annual locked-candidate slow-M1 checks** likewise matched exactly. The slow reference was reconstructed locally, **NOT the official complete GitHub checkout**.
- GitHub batch implementation: [batch_directional_run_h1_grid.py](../scripts/batch_directional_run_h1_grid.py). Locked official-checkout verification runner: [run_locked_fac011.py](../scripts/run_locked_fac011.py). Synthetic tests: [test_batch_directional_run_h1_grid.py](../tests/test_batch_directional_run_h1_grid.py).
- **CI VERIFIED for FAC011 code/tests:** GitHub Actions [run 40405257053](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40405257053) on code-containing commit `52cb21e031187862c013ffe2c7e18147c821fd66` **PASSED 713/713 tests**, compilation, dependency/CLI smoke and 26 synthetic reference/fast trade parity. **Still pending:** original private archive replay from a complete official repository checkout and canonical source-data parity. Any later registry-only commit needs its own head CI check.
- Private results bundle retains the full 19,200-by-12 monthly matrices for EACH year and locked 2014–2016 results. No private market quotes in the bundle.
- Multiple-testing and selection bias remain severe; 2012–2016 historically exposed. A truly prospective embargoed protocol, independent spread/tick source and actual shared-capacity portfolio are still required. Keep PR **Draft**, unmerged, no live trading.

### Additional local source-copy verification (after original report)

- **12 original-source design-year samples** (six per year, including the 23/24 variant and the sole screen pass) and **three locked 2014–2016 annual samples** matched a local copy of GitHub `fast_engine.run_fast` and a separate slow M1 reference. Every checked trade close, trade net, 12 monthly nets, fees, annual net, floating DD and **every observed M1 marked equity** matched within 1e-7; max source-copy-vs-slow floating M1 equity difference **2.85e-14**. This is NOT a complete official checkout or broker-tick validation. The local audit JSON is included in the private results bundle.
