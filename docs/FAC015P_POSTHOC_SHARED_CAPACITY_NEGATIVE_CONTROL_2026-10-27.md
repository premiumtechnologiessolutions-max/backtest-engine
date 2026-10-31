# FAC015P — post-hoc shared-capacity portfolio negative control (2026-10-27)

**Decision: REJECT / diagnostic only, not a validated strategy.** The two components were chosen **after seeing their individual exposed-year results**. Their exact combination and priority were frozen **before the combined results** at [commit 36f7528](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/36f7528e15cf9ded1d163adae1e9c11ece78f97d), [frozen protocol](FAC015P_FROZEN_POSTHOC_SHARED_CAPACITY_DIAGNOSTIC_2026-10-27.md). This is a single diagnostic replay per year, **not 2 more parameter specs, not 2 additional grid backtests, not independent OOS**.

**Components (both previously rejected):** FAC015 `SAC15_N12_C+0.00_B1.50_CALM_NY_LOCAL_0930_1330_SL1.50_TP2.25` and FAC014 `PDR15_K0.00_W4_FOLLOW_ALIGNED_HOT_ALL_SL1.25_TP1.00`. Exact prior logic and parameters unchanged. Stable confirmation sort, FAC015 first for ties; official `run_fast` **one position shared across both**, 1oz, next observed M1 open <=60s, stop-first, adverse gap-through, exactly **$0.40/oz ALL-IN roundtrip**. Original private ZIP SHA256 verified locally; no raw quotes published.

| Actual shared account | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Strictly positive UTC exit-booked months | **10/12** | **8/12** | **18/24** |
| Net after exact fee, $/oz | **+59.21625** | **+30.89375** | **+90.11000** |
| Filled trades (single account) | 122 | 128 | **250** |
| Fees, $/oz | 48.80 | 51.20 | **100.00** |
| Worst month, $/oz | -12.64750 | -15.18875 | **-15.18875** |
| Max annual observed M1 floating DD, $/oz | 23.57000 | 45.22375 | **45.22375** |
| Submitted component signals | 142 | 165 | 307 |
| Expired unfilled signals (capacity and/or gaps) | 20 | 37 | 57 |

2012 actual shared UTC monthly net ($/oz): `[12.21250,23.27250,5.77375,3.17500,1.96000,-2.73000,6.25625,-12.64750,4.95500,11.31125,2.69875,2.97875]`.

2013 actual shared UTC monthly net ($/oz): `[1.12250,10.12375,13.85875,-13.03625,-15.18875,8.45000,3.62875,17.01750,-6.19625,12.73500,-2.89750,1.27625]`.

**Why shared capacity matters:** summing two *separate* standalone P/L streams would falsely imply **+$100.53/oz** (+$105.07625 FAC015 and -$4.54625 FAC014). The **actual shared-capacity result is +$90.11/oz**, **$10.42/oz lower**, with different entry competition and trade counts. Do not present standalone sum as a portfolio. The 57 expired signals are not all proven to be capacity-only (market gaps may contribute).

**Reject despite historical +$90.11:** only 18/24 positive months, two negative months in 2012 and four in 2013, worst -$15.19/oz; both components were selected post-hoc after thousands of correlated trials and individually failed frozen gates. This is highly selection-biased and cannot forecast a future 12/12, cannot be called clean OOS, and is not authorized for live trading. No retuning, no broker tick execution certification.

**Independent execution verification:** two local independent slow M1 state-machine annual replays exactly matched the canonical shared-capacity `run_fast` at **all 705,292 observed M1 equity marks** (352,975 + 352,317), all 24 UTC monthly net values, **250 fills**, fee totals and expired signal counts; maximum per-mark and monthly differences **0**. Auditing code: `scripts/verify_fac015p_independent_slow.py`.

**Official GitHub checkout verification:** [Actions run 40428477922](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40428477922) passed **777/777 tests** on commit [ad9377e](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/ad9377edc29031d454580821973386e3c3aaa411). Downloaded verified source artifact `12701365168` and reran the **actual committed portfolio script** locally on SHA-verified original private M1: both years' full shared monthly net, fills, fees, worst month and floating DD exactly reproduced (maximum numeric difference <1e-8). Subsequent auditor/report metadata commits require separate current-head CI confirmation.

Code: `scripts/run_fac015p_shared_portfolio.py`; frozen protocol: `docs/FAC015P_FROZEN_POSTHOC_SHARED_CAPACITY_DIAGNOSTIC_2026-10-27.md`. This single-account audit does **not** change FAC015 factory totals.