# NRF-FAC-015 — 72,000 annual M1 sign-autocorrelation fade replays (2026-10-27)

**Decision: REJECT.** New hypothesis is a rolling completed-M15 candle-body **lag-one sign-autocorrelation fade**, with last completed H1 range regime and IANA-DST local sessions. This is **not** RSI, Donchian, prior-day reclaim, compression, or FAC013 liquidity sweep. The preregistered frozen hypothesis and grid were committed **before original-data outcomes** at [55ca1fd](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/55ca1fd024dc691ec9fc98b2ba82fb5241a0c162), [frozen spec](FAC015_FROZEN_M15_SIGN_AUTOCORR_FADE_2026-10-27.md).

## Data, causality and execution

- Locally verified original private `Gold data.zip` SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Never uploaded raw BID/ASK quotes or trade timestamps to public GitHub or Actions.
- Exact **$0.40/oz ALL-IN roundtrip**, one 1oz position, next observed eligible M1 open <=60 seconds after completed M15 confirmation, stop-first ambiguous M1 bars, adverse open gap-through, no fabricated missing minutes, no future H1 or rolling observations. M1 floating equity marks include the fee; UTC exit-booked months; annual resets.
- **36,000 correlated parameter specs**, not 36,000 independent statistical hypotheses: 5 correlation windows × 4 correlation bounds × 3 candle-body filters × 2 H1 regimes × 3 sessions × 10 stop × 10 target multipliers. **2012/2013 historically exposed**; not clean OOS, broker ticks, or a portfolio.

## Actually completed design-year executions

| Metric | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Parameter specs | 36,000 | same IDs | **36,000 distinct** |
| Executed annual M1 replays | 36,000 | 36,000 | **72,000** |
| Active annual replays (filled trades) | 36,000 | 36,000 | **72,000** |
| Exit-booked monthly P/L observations | 432,000 | 432,000 | **864,000** |
| Positive annual-net configurations | 3,015 | 2,857 | **931 same IDs positive both** |
| Distinct causal entry streams | 360 | 360 | correlated |
| Best strictly positive months | 11/12 | 11/12 | **21/24 for same ID** |
| Configurations with 24/24 | — | — | **0** |
| Configurations passing preregistered joint gate | — | — | **0** |

**Frozen joint gate:** >=100 filled trades **each year**, >=18/24 positive UTC months, net >0 in both years, worst month >=-$20/oz, maximum annual observed M1 floating drawdown <=$100/oz. Only 41 parameter specs reached >=18/24 positive months, but **none passed all gates**. Zero-trade controls: **0**. No gate was relaxed after outcomes.

## Highest positive-month count (post-hoc, REJECT)

`SAC15_N12_C+0.00_B1.50_CALM_NY_LOCAL_0930_1330_SL1.50_TP2.25`

| Metric | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Positive UTC months | 10/12 | 11/12 | **21/24** |
| Net after all-in fee, $/oz | +49.42750 | +55.64875 | **+105.07625** |
| Filled trades | **62** | **77** | 139 |
| Fees, $/oz | 24.80 | 30.80 | **55.60** |
| Worst UTC month | -11.37125 | -15.86750 | **-15.86750** |
| Max annual M1 floating DD, $/oz | <=26.69625 | <=26.69625 | **26.69625 max** |

2012 Jan–Dec exit-booked net ($/oz): `[8.84125,21.36125,11.14625,11.42875,0.01000,-5.93625,5.36875,-11.37125,2.25500,3.44625,0.83875,2.03875]`.

2013 Jan–Dec exit-booked net ($/oz): `[0.12250,9.07750,14.88125,-15.86750,2.30500,1.40500,9.82125,10.43250,5.28000,11.25000,1.99000,4.95125]`.

**Reject:** 62 and 77 fills versus frozen >=100 per year. The 21/24 result is **post-hoc selected among 36,000 correlated specifications**, so cannot be interpreted as a 21/24 forecast. A higher-frequency variant with >=100 fills both years reached at most **17/24**, also rejected. Highest total-net variant +$145.73625/oz reached 19/24 but had only 75/86 fills and worst month -$21.84250: rejected.

## Verification and limitations

- Each annual run generated 12 monthly net values, trades, exactly 0.4 × filled-trade fee, worst month and observed M1 floating DD. Every row passed monthly-sum and fee reconciliation.
- **8 deterministic canonical `run_fast` full-year parity samples** (4/year), including highest monthly-count in each year, passed on the original private M1 with **zero** discrepancy in monthly net, fees, fills and M1 DD.
- Additional **2 full-year independent slow M1 state-machine** checks for the combined 21/24 post-hoc example reproduced **all 705,292 observed M1 floating-equity marks exactly (max difference 0)**, 139 filled trades, 24 monthly P/L values, fees and totals. This is engine parity, **not** broker tick fills or statistical validation.
- **Official GitHub Actions passed 777/777 tests on commit [`885c3df`](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/885c3dfbba946d7beead1b6b35eb319157a1cae4), [run 40427991598](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40427991598).** The successful run's verified public-source artifact `12700856953` was downloaded and replayed locally against the SHA-verified private original ZIP: **all 72,000 annual outcomes (36,000 per year), all 864,000 monthly P/L values and every numeric row field matched the earlier local research exactly, maximum numerical difference 0**. Eight official `run_fast` sample checks passed in the replay. The additional two independent slow M1 audits checked 705,292 equity marks. No raw quotes were uploaded. The earlier local full-suite attempt without optional `pyarrow` failed on a Parquet dependency test; the official constrained CI installed dependencies and passed.
- No new shared-capacity multi-strategy portfolio was promoted: **0/36,000 passed the frozen candidate gate**. Never add separate strategy P/L to imply executable portfolio results. No independent prospective / embargoed period is yet available. No live trading.

**Result:** keep FAC015 rejected; preserve negative outcomes, no retuning the selected 21/24 parameter. Draft PR stays open and unmerged.
**Reproducibility:** local CSV SHA256 2012 `b5bc1ce2fb2fd414b0f43dc8c5e546ceb902d7fe04edb06a975b830ec6e06728`; 2013 `c27bf02eecf029794ea356d07d931a0453c49cf01403bcbd954f9a9b2fc8abdb`. Official source artifact 2012 and 2013 outputs were compared row-by-row against these originals; all numeric values equal. Subsequent metadata-only branch commits need their own current-head CI verification.
