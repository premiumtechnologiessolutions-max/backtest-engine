# FAC022 — Frozen M5 path efficiency: 4,608 original-data annual M1 replays, REJECT

2026-10-27 UTC. **Preregistered before FAC022 outcomes** at commit `916d43c241be2478b535118f17c5d65ba34f4c01`. Frozen hypothesis: six-change completed M5 signed path efficiency, prior-20 complete M5 median range, completed H1 volatility halt, DST-aware session, **30-minute cooldown after the per-rule H1/session gate**, fixed $0.40/oz ALL-IN roundtrip. This is **ONE correlated family**, not 2,304 independent hypotheses. 2012/2013 are historically exposed, NOT clean OOS.

## Pre-outcome feasibility
The SHA256 of private original `Gold data.zip` was verified locally as `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Same-ID signal-only preflight found 2012 max **2,970** and 2013 max **3,073** eligible events; **34/36 same rule IDs** had >=100 signals in both years. This allowed the frozen exit grid. A signal is not a filled trade.

## Completed local replay (private original source)
| Measure | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Correlated parameter specs | 2,304 | 2,304 | **2,304 distinct specs** |
| Annual M1 replays executed | 2,304 | 2,304 | **4,608** |
| Active annual M1 replays | 2,304 | 2,304 | **4,608** |
| Zero-trade annual replays | 0 | 0 | **0** |
| Exit-booked monthly P/L cells | 27,648 | 27,648 | **55,296** |
| Maximum positive months within year | 8/12 | 8/12 | — |
| Maximum same-ID positive months | — | — | **15/24** |
| Same-ID configs >=18/24 months | — | — | **0/2,304** |
| Frozen joint gate passes | — | — | **0/2,304** |

Best **by positive-month count only**, not an accepted strategy: `PE5_K0.70_FADE_CALM_NY_LOCAL_0930_1330_SL2.00_TP1.75`. 2012: **8/12 months**, **95 fills**, **-$19.14625/oz**; 2013: **7/12 months**, **140 fills**, **-$38.24625/oz**. Combined **15/24 months, -$57.39250/oz after $94.00 in fees**; worst UTC month **-$26.195/oz**; max observed annual M1 floating DD **$49.375/oz**. **REJECT**: fails monthly, annual net, 2012 fill-count and worst-month gates.

Frozen individual gate passes among 2,304 correlated specs: >=100 fills both years **2,134**; >=18/24 positive months **0**; positive annual net both **0**; worst month >=-$20/oz **484**; annual floating DD <=$100/oz both **537**. Joint passes **0**. No parameter retuning.

## Execution and parity
Original private ZIP verified by SHA256; observed M1 only, no fabricated minutes; next eligible open <=60s, stop-first, adverse gap-through, exactly $0.40/oz all-in. **8 local canonical run_fast** full-year samples (4/year) match annual trades, monthly booked P/L, fees and M1 floating DD exactly. **2 independent slow execution.run vs run_fast** full-year samples on the exploratory highest-months ID match all 15 trade fields and **705,292 observed M1 equity marks / 235 fills**, maximum M1 equity delta 0. Full-year source years have 352,975 and 352,317 observed M1 marks.

**Implementation audit:** an early local exploratory replay applied cooldown *before* per-rule session filtering, inconsistent with the already-frozen specification. It was explicitly invalidated and **excluded from all counts**. The corrected runner applies cooldown **after** each rule's causal H1/session filter. Both complete years were rerun on the corrected implementation; all results and numbers above refer exclusively to the corrected frozen logic. The hypothesis, grid and gate were NOT changed to fit outcomes.

## Limits and pending
**Official-source full-grid reproduction COMPLETED:** successful GitHub Actions source run [40531528349](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40531528349) on commit `f6d625cdef6dcccfdce379fd72b2d1865e41068a` passed **1,138/1,138 tests**. Downloaded exact CI source artifact `12746092395` (ZIP SHA256 `3d472b522dc4d257a189ef6837dfa442b74e86847275056cd58dbed9eea3960f`), reran its frozen FAC022 runner locally on the original private SHA-verified ZIP. **All 4,608 annual parameter rows and 55,296 monthly P/L values matched the initial corrected local outputs exactly, with every ID equal and maximum numeric delta 0.** Evidence: `research/FAC022_OFFICIAL_SOURCE_REPLAY_VERIFICATION_2026-10-27.json`. Subsequent registry/report-only head CI must be checked separately. Results are historically exposed, not prospective OOS; no independent BID/ASK tick/slippage proof, no approved shared-capacity portfolio and no profitable-month claim. Separate strategy profits are never summed into a portfolio. Raw private BID/ASK/M1, trade ledgers and source ZIP were **not uploaded**. PR #1 stays Draft/unmerged; no billing/privacy or live trading changes.
