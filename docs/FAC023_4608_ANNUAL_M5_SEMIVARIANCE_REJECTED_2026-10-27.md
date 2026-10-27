# FAC023 — Official original-source 4,608 annual M1 replays — REJECT (2026-10-27)

**Preregistered before opening outcomes:** commit [c4d8d8b](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/c4d8d8b67e69b7b20a4615f25077441c155a15e1), [frozen spec](FAC023_FROZEN_M5_SEMIVARIANCE_TRANSITION_2026-10-27.md). **One** distinct signed-M5-realized-semivariance transition hypothesis, 36 correlated entry rules ×64 stop/target exits = **2,304 related specs**, NOT 2,304 independent hypotheses. Both years 2012 and 2013 historically exposed design, NOT clean OOS.

## Real executed batch and frozen gate
- SHA256-verified original private Gold data.zip `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` loaded locally only. Signal-only preflight, no exit outcomes: all **36/36** SAME rule IDs had >=100 potential signals in BOTH years (max 3,109 in 2012; 3,106 in 2013), so the exit sweep was structurally eligible.
- Completed **2,304 active annual M1 replays per year**, **4,608 total**; **0** zero-trade replays; **55,296 exit-booked monthly net P/L cells**. All **2,304** combined 2012+2013 net totals were **negative**, with the least negative **-$39.18/oz**. 2012 max 8/12 profitable months, 2013 max 5/12; best SAME spec **12/24**, **0 >=18/24**, **0 positive net in BOTH years**, **0 frozen joint passes**, **0 at 24/24**.
- Highest-months exploratory spec `SV5_K0.40_FADE_CALM_NY_LOCAL_0930_1330_SL2.25_TP2.25`: **7/12** profitable 2012, **5/12** 2013; **121/165 actual fills**; annual net **-$24.0100/oz / -$62.1525/oz**; combined **-$86.1625/oz after $114.40/oz all-in fees**; worst month **-$26.8175/oz**, max annual observed M1 floating DD **$90.28/oz**. Despite adequate fills, violates frozen monthly/annual/worst-month gates. **REJECT, no retuning**.
- Best combined net spec `SV5_K0.55_FADE_CALM_NY_LOCAL_0930_1330_SL2.00_TP2.25` still **-$39.18/oz** over 2012/13, **9/24** profitable months, 98/139 fills, worst month -$21.225/oz, floating DD $63.54875/oz. Not a candidate.

## Monthly net P/L for highest-months spec, USD per ounce, AFTER fees
| UTC month | 2012 | 2013 |
|---|---:|---:|
| Jan | +9.9800 | +9.7588 |
| Feb | +7.6375 | +5.4450 |
| Mar | -19.2163 | -3.2412 |
| Apr | +14.6100 | +6.7013 |
| May | +7.3475 | +0.6063 |
| Jun | **-26.8175** | -15.8888 |
| Jul | +0.8600 | -18.0625 |
| Aug | -7.5500 | -9.8925 |
| Sep | -5.2675 | -18.7763 |
| Oct | -14.8025 | +4.1850 |
| Nov | +1.5075 | -11.0050 |
| Dec | +7.7013 | -11.9825 |

Monthly table rounded to four decimals for display; all reconciliation used original unrounded CSV amounts.

## Execution, reproducibility, and limitations
- Official GitHub CI source artifact **12753929062** from [successful workflow 40550223574](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40550223574), source commit `cead7679bdf5d9944cbb137d30fea758459ca400`, **1,156/1,156 pytest passed**. Replayed complete 2012 and 2013 grids locally on original SHA-verified ZIP. **All 4,608 annual rows and 55,296 monthly values reproduced byte-identically** against the earlier local outputs; zero CSV delta. Each year passed 4 `run_fast` canonical full-year parity samples (8 total), including exit-booked monthly P/L, fill counts, fees and floating DD.
- Two **independent slow execution.run vs run_fast January-only segments**, one each for 2012/13, agreed exactly across **17 fills, all 15 trade fields, and 58,697 observed M1 equity marks**. This is explicitly **NOT full-year slow parity**; do not inflate the claim. See [aggregate verification](../research/FAC023_OFFICIAL_SOURCE_REPLAY_VERIFICATION_2026-10-27.json).
- Fixed exactly **$0.40/oz ALL-IN roundtrip**, next eligible M1 open <=1 minute, stop-first, adverse gap-through, no fabricated minutes. Private original BID/ASK M1 archive and trade-level ledgers were **not** uploaded. No independent prospective OOS, broker tick validation, or approved shared-capacity portfolio. Since every spec loses across both design years and no frozen gate passes, **no portfolio claim is made** and no posthoc portfolio is selected.

**Decision:** FAC023 REJECTED on historically exposed design. Do not retune it. Keep PR Draft/unmerged, no real trading, no billing/privacy change.
