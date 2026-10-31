# NRF-FAC-013 — 43,200 completed original-source annual M1 replays (2026-10-27)

**Decision: REJECT entire preregistered family for frozen joint acceptance.** Historical design exploration only; 2012–2013 were exposed before the search. No clean OOS, no live fill proof, no 12/12 guarantee.

## Preregistration and provenance

- Frozen **before examining FAC013 results** at commit [d1efaa8](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/d1efaa8dc43b61583f0c2aee45460ea59123bd1f), document `docs/FAC013_FROZEN_M15_LIQUIDITY_SWEEP_H1_2026-10-27.md`.
- Official complete source snapshot from successful GitHub Actions run **40413939371**, source commit `8d296673940315310b3794cd00863da4abd3cb40`, was used locally, with the new preregistered FAC013 runner. No private quotes were sent to GitHub or Actions.
- Original `Gold data.zip` verified locally as SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
- Fully observed M1 BID reference OHLC, next eligible observed M1 open within 60s, one position, stop-first, adverse gap-through, no fabricated minutes, exactly **$0.40/oz ALL-IN roundtrip**. Monthly results are UTC exit-booked. M1 floating DD includes the full fee.

## Completed bulk grid, not independent hypotheses

| Metric | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Distinct parameter specifications | 21,600 | same 21,600 | **21,600** |
| Actually executed annual M1 replays | 21,600 | 21,600 | **43,200** |
| Active annual replays with fills | 21,600 | 21,600 | **43,200** |
| Zero-trade annual replays | 0 | 0 | 0 |
| Exit-booked monthly P/L values | 259,200 | 259,200 | **518,400** |
| Positive annual net specs | 3,083 | 3,859 | 1,435 positive in BOTH |
| Maximum positive months in one year | 11/12 | 12/12 (1 spec) | **18/24** |
| Unique causal signal streams | 215 | 216 | Not independent hypotheses |

Across the same 21,600 specs: **8 achieved >=18/24 positive months; 0 achieved 24/24; 0 passed all frozen gates.** No claim of 21,600 statistically independent hypotheses.

## Highest monthly-consistency exploratory parameter (REJECT)

`SWEEP15_N36_K0.25_AGAINST_H1_CALM_ALL_SL1.75_TP2.75` was selected **post hoc** from the completed grid and cannot be called independently validated.

| Metric | 2012 | 2013 | Total / maximum |
|---|---:|---:|---:|
| Positive UTC months | 8/12 | 10/12 | **18/24** |
| Net after exact fee ($/oz) | +16.81375 | +46.75875 | **+63.57250** |
| Filled trades | 53 | 49 | **102** |
| Total roundtrip fees ($/oz) | 21.20 | 19.60 | **40.80** |
| Worst month ($/oz) | -10.265 | -7.955 | **-10.265** |
| Max annual observed M1 floating DD ($/oz) | 21.1575 | 16.2625 | **21.1575** |

Frozen acceptance required **>=80 trades in EACH year** as well as >=18/24 months, net positive both years, worst month >=-$12 and DD <=$80. The displayed setting FAILS sample-size gate (53,49), and **must not be adapted/retested to make it pass**.

Exit-booked monthly net ($/oz):
- 2012 Jan–Dec: `+4.621, +8.447, -5.138, +9.963, -10.265, +6.360, -0.621, +0.950, -4.791, +2.184, +4.365, +0.739` (display rounded; CSV is full precision).
- 2013 Jan–Dec: `+1.839, -2.789, +2.945, -7.955, +2.755, +13.573, +18.379, +0.144, +9.815, +1.210, +0.573, +6.271` (display rounded; CSV is full precision).

## Execution and parity evidence

- Frozen `scripts/batch_liquidity_sweep_h1_grid.py` completed 21,600/21,600 specs on each original private annual M1 slice. Each annual summary includes the loaded BID/ASK M1 fingerprint, 12 monthly outcomes per spec, fee, trade count, worst month and M1 floating DD.
- **8 deterministic original-source `run_fast` annual parity samples** (first, middle, last, annual highest-months each year), exact 12-month P/L, total net, fees, trades and floating M1 DD within `1e-7`; observed maximum difference **0** for those 8 samples.
- **2 additional full-year independent `execution.run` vs `run_fast` audits** for the highest 24-month consistency setting: 53 trades and 352,975 observed M1 equity marks in 2012; 49 trades and 352,317 marks in 2013. All trade-ledger fields and every observed floating equity mark matched (maximum equity difference **0**); month error <=`1.78e-15`.
- 4 new frozen logic/causality/gap unit tests passed locally. Full local suite had **727 passed, 8 blocked/failed solely due missing optional `pyarrow`** in this container (not strategy assertions); rely on subsequent full GitHub Actions with pinned dependencies for the current code commit and record its actual result separately.
- CSVs and summaries for all 43,200 annual replays were retained locally and supplied separately; **raw original quotes never committed**.

## Scientific limitations and next work

The fee model is a synthetic fixed all-in assumption, not a broker spread/slippage or tick reconstruction. M1 OHLC ambiguity is stop-first, but true tick ordering remains unknown. Historical selection bias and multiple-testing burden invalidate claims of reliable future monthly profits. No candidate passed the preregistered sample-size/consistency gate, so **no new shared-capacity portfolio is authorized from FAC013 winners**. Next independent work: precommit a portfolio with fixed components and one capital account, or prospective forward observation with embargo and no post-hoc tuning. PR stays Draft/unmerged; no live trading.

## CI reconciliation (2026-10-27)

An intermediate current-head GitHub Actions run [40419571881](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40419571881) **FAILED: 734 passed, 1 failed**, because the newly added test used an incorrect dictionary key for the frozen fee constant. This was a test-only typo; no strategy or replay results were changed. The test key was corrected in commit [7d1b8b5](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/7d1b8b5d4071a3338b6eb14b450f36ddf6b4f137). GitHub Actions [run 40419755915](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40419755915) **SUCCESS: 735/735 pytest**, compile, constrained dependencies and synthetic CLI smoke. This CI does not contain private original gold quotes; those parity replays ran locally only. Later report/registry-only commits may require their own CI confirmation.
