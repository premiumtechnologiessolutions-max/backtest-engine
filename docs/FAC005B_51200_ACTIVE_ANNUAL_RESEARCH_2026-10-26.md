# NRF-FAC-005B — 51,200 original-data active annual replays, 2012–2013 (2026-10-26)

**Research status: historically exposed, post-FAC005 data-coverage follow-up; NOT independent OOS, NOT approved for live trading.**

## Frozen before these results
[FAC005B gap-aware H1 range/EMA hypothesis](FAC005B_FROZEN_GAP_AWARE_H1_RANGE_M15_EMA_2026-10-26.md) committed at `da11f721668969863dde4498c4854f8b9a08180b`, before FAC005B original-source results. This follow-up was motivated by FAC005's **zero valid H1 regimes** caused by daily market quote gaps; it is **not** an independent discovery. The original FAC005 remains frozen and [rejected as zero-trade](FAC005_SESSION_GAP_ZERO_TRADE_REJECTION_2026-10-26.md).

The exact GitHub Actions CI-tested source snapshot `a5f7a43bd578344563e0efda1fc0c6603972db1c` passed **647/647 pytest** plus synthetic installed CLI at [run #40388775088](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40388775088). This exact snapshot was executed privately against original `Gold data.zip`, verified SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Original raw BID/ASK M1 rows were **never uploaded to public GitHub**.

The follow-up's 4×4 EMA spans and 4 H1 range-ratio gates produce 64 genuinely distinct entry-signal sequences in each year. Each ×20 stop distances ×20 target distances yields 25,600 **correlated parameter specs/year**. All 51,200 annual backtests **actually executed with at least one filled trade**, yielding 614,400 exit-booked monthly net P/L cells. 12 original-source `run_fast` parity samples (6/year) matched monthly P/L, filled count, fee, annual net, M1 floating maximum drawdown to 1e-7.

| Statistic | 2012 | 2013 |
|---|---:|---:|
| Original observed M1 bars | 352,975 | 352,317 |
| Complete M15 bars | 23,197 | 23,023 |
| Complete H1 bars | 5,600 | 5,486 |
| Annual parameter backtests, all nonzero trade | 25,600 | 25,600 |
| Net-positive after $0.40/oz ALL-IN fee | 7,354 | 9,280 |
| Maximum positive months / 12 | **11** | **12** |
| Variants 12/12 positive | **0** | **28** |
| Original canonical parity samples | 6 | 6 |

### Exact parameter-ID cross-year join
- **4,712/25,600** parameter IDs positive annual net in **both** separately reset years.
- **318** variants >=18/24 positive calendar months; **64** variants >=20/24.
- **183** variants >=18/24 positive months **and** annual net-positive in both years; **27** variants >=20/24 and annual net-positive both years.
- Maximum **22/24** positive months; **0** at 23/24 or 24/24.
- The 22/24 candidate `RANGEH1_EMA15_F08_S72_G1.00_SL9.50_TP1.00` took only **44 trades (2012)** and **25 trades (2013)**. It **LOST -$5.10/oz in 2012** despite 10/12 positive months, and gained +$15.00/oz in 2013 with 12/12 positive months. 2012 worst month -$16.20 and floating M1 max DD $25.36; 2013 floating DD $9.80.
- The best both-years-annual-positive monthly count was **21/24**: `RANGEH1_EMA15_F08_S72_G1.00_SL6.50_TP1.00` (44 and 25 trades), **2012 +$3.90/oz, 2013 +$7.50/oz**, worst month -$10.20, annual M1 max floating DD $16.43 and $8.90. **Only 69 trades across two years**, an extremely weak basis for monthly-profit claims.
- Requiring >=100 trades in **each** year and positive net both years lowers the best positive-month score to **18/24**; example `RANGEH1_EMA15_F16_S26_G0.80_SL8.00_TP10.00` filled 239/218, gained +$107.67/+12.26 per oz, worst month -$76.41 and M1 floating DD up to $111.34/oz.

### Post-selection cost sensitivity (NOT OOS)
At the frozen $0.40/oz roundtrip, the 21/24 both-years-positive candidate gained +$3.90 (2012) and +$7.50 (2013). At **$0.80/oz**, same signals/fills instead **LOST -$13.70 (2012)** and **-$2.50 (2013)**. At $1.20/oz, it lost -$31.30 and -$12.50. The higher-trade 18/24 candidate turns 2013 negative at $0.80/oz. These are scenario stresses, **not an added spread/fee on the base $0.40 model**.

The full per-parameter monthly/yearly CSVs, exact-ID join, exploratory top-25, selected cost-stress, original-source summary hashes and CI source snapshot are in private bundle `NoRiskFX_FAC005B_51200_Active_Annual_Backtests_2026-10-26.zip`; no original market quotes.

**Conclusion:** Do not promote a strategy. This family has some appealing historical monthly-hit scores but extremely sparse trades for top variants, severe fee sensitivity, correlated grid-selection bias, exposed years and no broker-tick execution evidence. The 2013-only 12/12 result is not replicated in 2012. Next: jointly constrained shared-capacity portfolio and independent forward validation.
