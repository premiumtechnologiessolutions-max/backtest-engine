# FAC021 — Frozen signed M15 CUSUM: original-data 4,608 annual M1 replays, REJECT
2026-10-27 UTC. Frozen **before outcomes** at commit `fb4e007f08547e078801a52bbfaf13a755205f23`; source SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. All source prices stayed local.

## Design and signal-only feasibility
The frozen sequential signed CUSUM uses completed contiguous M15 bars, median of the prior 20 M15 ranges, a reset at threshold and after gaps, completed H1 volatility regime and DST-aware London/NY session. One hypothesis family: **36 correlated entry-rule groups × 64 exit pairs = 2,304 correlated parameter specs/year**. 2012/2013 are historically exposed and are not clean OOS.

The pre-outcome, no-P/L signal-only test found 2012 max **1,264** eligible signals, 2013 max **1,209**. **30 of 36 SAME entry-rule IDs** had at least 100 signals in EACH year, so the frozen full exit sweep was allowed. Neither year's signal count is a fill count.

## Completed local replay on private original ZIP
| Measure | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Annual parameter replays executed | 2,304 | 2,304 | **4,608** |
| Annual replays with >=1 trade | 2,304 | 2,304 | **4,608** |
| Zero-trade annual replays | 0 | 0 | 0 |
| Monthly exit-booked net P/L cells | 27,648 | 27,648 | **55,296** |
| Highest positive months within year | 10/12 | 10/12 | — |
| Highest same-ID positive months | — | — | **17/24** |
| Same-ID settings >=18/24 positive months | — | — | **0/2,304** |
| Frozen joint acceptance passes | — | — | **0/2,304** |

Best **by positive-month count** (not an accepted candidate):
`CUSUM15_K2.50_FADE_CALM_NY_LOCAL_0930_1330_SL1.50_TP0.50`: **17/24 positive months**; 2012 **24 fills, +$0.675/oz**; 2013 **34 fills, +$8.98/oz**; combined **58 fills, +$9.655/oz** after exactly **$23.20/oz all-in roundtrip fees**; worst UTC exit-booked month **-$4.36/oz**; max observed annual M1 floating DD **$9.015/oz**. **REJECT**: 17<18 months and 24/34<100 filled trades/year. No retuning.

Individual frozen gate counts: >=100 fills in both years **1,920/2,304**; positive net in both years **23/2,304**; >=18/24 positive months **0/2,304**; worst month >=-$20/oz **753/2,304**; annual observed M1 floating DD <=$100 in both years **985/2,304**. Zero joint passes. Historical candidate rankings have severe multiple-testing and sample-size limitations.

## Execution and parity evidence
Original `Gold data.zip` SHA256 checked locally. Exactly $0.40/oz roundtrip; observed M1 only; next eligible open <=1 minute; stop-first, adverse gap-through; no fabricated minutes or lookahead. **8 local canonical run_fast samples** (4/year) reconciled exit-booked monthly P/L, trade count, fees, net, and floating M1 DD with the normalized batch engine, zero differences. **2 independent slow execution.run vs run_fast full-year samples** on the 17/24 exploratory setting reconciled **58 fills and 705,292 observed M1 equity marks**, with exact trade fields and zero equity differences. The private source and raw M1/quotes were not uploaded.

**Not established:** an independently selected executable cross-strategy shared-capacity portfolio; independent tick BID/ASK/slippage parity; untouched prospective OOS; 12/12 monthly profitability; live viability. No summing of separate strategy profits. This is a rejected exposed-history research family.

## Audit boundary
Local replay was executed using the official repository source artifact at previous exact-head `19a556c` plus the newly preregistered FAC021 runner. The FAC021 source/tests have been committed to the branch; **new exact-HEAD GitHub CI and complete official FAC021-source artifact re-execution must be verified separately before registry promotion**. No new accepted trading strategy. PR #1 remains Draft/unmerged; no billing/privacy or live-trading changes.
