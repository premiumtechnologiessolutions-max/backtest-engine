# FAC027 original-source 2012/2013 rejection — 2026-10-30

**Decision: REJECT for monthly stability.** This is a frozen *one-family* design with **16 correlated parameter specifications**, not 16 independent hypotheses. Pre-results hypothesis/grid committed as [11fb7808](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/11fb7808fe61090c9ab380d3f8f8726b218066a8) **before opening strategy P/L**. No post-result grid changes.

## Source, execution and reproducibility
- Private original ZIP SHA256: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`, locally verified; **no raw quote uploads**.
- Exact committed executable: `scripts/research_fac027_london_asia.py`; Git blob SHA `a0e1112c2cfd1fbda2d469332c7c34b793ebe214` matches the locally executed file byte-for-byte.
- 2012: 352,975 observed M1 bars, 190 complete 00:00–08:00 NY source sessions. 2013: 352,317 M1 bars, 139 complete source sessions. Missing minutes were not fabricated; session coverage is a significant limitation.
- Two deterministic full local executions of **16 configurations × 2 years = 32 annual M1 BID-reference replays**, **384 monthly realized P/L values**; aggregate full local result JSON SHA256 `e6cfd5eb552dd1fb6f54755dbdee47b2aaa87759352dfd6cd5588ae4ac410d24`. Synthetic execution tests: **8/8 locally passed**. Separate canonical engine parity is **NOT yet established**.
- Actual observed next 08:01 NY M1 open or no trade, M1 stop-first, adverse open gap-through, 11:00 NY time exit at observed open, exactly **$0.40/oz ALL-IN roundtrip**, UTC exit-month booking, M1 observed close-equity drawdown. BID-reference is **not authenticated broker BID/ASK execution**. Full 12-month zero-trade inclusion; no OOS.
- 16 independent per-setting annual replays are **not** a diversified portfolio. Additional diagnostic shared one-position, lexicographic-frozen-grid priority portfolio is run separately below. The shared priority rule is a deterministic diagnostic, **not a newly validated post-selection portfolio**.

## All 16 correlated settings: 2012/2013 results

Columns: [Asia buffer, London efficiency, SL×H1 risk, TP×H1 risk], trades 2012/2013, positive months 2012/2013, annual net USD/oz 2012/2013, two-year net USD/oz, worst month USD/oz, larger observed annual M1 drawdown USD/oz.

| Config | Trades | Positive months | Annual net 2012 / 2013 | Two-year net | Worst month | Max annual M1 DD |
|---|---:|---:|---:|---:|---:|---:|
| .05,.30,.8,1.0 | 96/75 | 3/6 | -65.368 / +0.778 | -64.590 | -20.544 | 81.228 |
| .05,.30,.8,1.5 | 96/75 | 3/6 | -100.439 / +1.616 | -98.823 | -23.060 | 116.092 |
| .05,.30,1.2,1.0 | 96/75 | 3/5 | -94.710 / -2.050 | -96.760 | -26.274 | 109.770 |
| .05,.30,1.2,1.5 | 96/75 | 1/5 | -150.768 / +5.696 | -145.072 | -28.006 | 163.318 |
| .05,.50,.8,1.0 | 67/51 | 4/6 | -37.822 / +9.750 | -28.072 | -16.900 | 52.404 |
| .05,.50,.8,1.5 | 67/51 | 4/5 | -68.078 / -6.082 | -74.160 | -18.544 | 80.628 |
| .05,.50,1.2,1.0 | 67/51 | **5/8** | -55.384 / +12.834 | -42.550 | -19.506 | 72.116 |
| .05,.50,1.2,1.5 | 67/51 | 2/6 | -107.247 / +7.520 | -99.727 | -22.830 | 119.797 |
| .15,.30,.8,1.0 | 93/71 | 3/6 | -57.668 / -2.564 | -60.232 | -19.444 | 73.528 |
| .15,.30,.8,1.5 | 93/71 | 3/7 | -92.739 / -5.801 | -98.540 | -22.128 | 108.392 |
| .15,.30,1.2,1.0 | 93/71 | 3/6 | -84.110 / -3.788 | -87.898 | -25.174 | 99.170 |
| .15,.30,1.2,1.5 | 93/71 | 1/5 | -140.168 / -0.117 | -140.285 | -28.006 | 152.718 |
| .15,.50,.8,1.0 | 66/49 | 4/6 | -36.722 / +9.808 | **-26.914** | -15.800 | 51.304 |
| .15,.50,.8,1.5 | 66/49 | 4/6 | -66.978 / -7.999 | -74.977 | -18.544 | 79.528 |
| .15,.50,1.2,1.0 | 66/49 | 5/7 | -54.284 / +14.496 | -39.788 | -19.506 | 71.016 |
| .15,.50,1.2,1.5 | 66/49 | 2/7 | -106.147 / +7.207 | -98.940 | -22.830 | 118.697 |

**All 16 settings lose across the two exposed years**. Maximum positive months is **13/24**, itself a loss of **-$42.550/oz**. The least-negative two-year result is **-$26.914/oz**, with only **10/24** positive months. Sample sizes range **115–171 trades** per setting across two years; all fail monthly stability.

## Actual one-slot shared-priority portfolio

Priority is fixed frozen GRID enumeration, first causal eligible configuration per NY day. Correlated settings do **not** stack capital or P/L. This priority collapses to the broadest first setting in this data; it is **not 16 diversified alphas**.

| Metric | 2012 | 2013 |
|---|---:|---:|
| Executed trades | 96 | 75 |
| Positive UTC months | 3/12 | 6/12 |
| Net after fees USD/oz | **-65.368** | **+0.778** |
| Fees USD/oz | 38.400 | 30.000 |
| Worst month USD/oz | -20.544 | -4.874 |
| Max observed M1 close-equity drawdown USD/oz | 81.228 | 16.414 |

**Total shared capacity: 171 trades, 9/24 positive months, net -$64.590/oz, total fees $68.40/oz. REJECT.** Separate-year drawdowns must not be summed or represented as one continuous account.

### Complete shared-portfolio UTC monthly net and observed month-local M1 drawdown (USD/oz)

| UTC month | Net | Month-local M1 DD |
|---|---:|---:|
| 2012-01 | -6.900 | 13.136 |
| 2012-02 | +2.494 | 5.516 |
| 2012-03 | -8.356 | 15.744 |
| 2012-04 | -6.960 | 8.998 |
| 2012-05 | -10.304 | 14.964 |
| 2012-06 | +4.430 | 7.628 |
| 2012-07 | -1.136 | 7.048 |
| 2012-08 | -5.684 | 13.816 |
| 2012-09 | -9.820 | 9.820 |
| 2012-10 | -7.682 | 10.172 |
| 2012-11 | **-20.544** | **24.330** |
| 2012-12 | +5.094 | 5.276 |
| 2013-01 | +3.678 | 6.176 |
| 2013-02 | -2.510 | 9.072 |
| 2013-03 | +4.934 | 6.304 |
| 2013-04 | +0.150 | 7.372 |
| 2013-05 | +0.734 | 4.470 |
| 2013-06 | -4.874 | 8.854 |
| 2013-07 | +7.088 | 4.816 |
| 2013-08 | -3.388 | 9.182 |
| 2013-09 | +2.466 | 4.154 |
| 2013-10 | -3.912 | 13.562 |
| 2013-11 | -3.268 | 8.334 |
| 2013-12 | -0.320 | 4.750 |

## Research integrity boundary

**Rejected, not optimized.** 2012–2016 were already historically exposed; there is no clean OOS claim. These 32 annual replays are provisional additional design research and must **not** inflate the canonical factory's previously audited active totals. The exact-code local replay is reproducible but **canonical run/run_fast parity, broker BID/ASK receipts, intrabar tick paths, and independent prospective OOS remain pending**. Month-local M1 drawdown is based on observed M1 close-equity/exit marks, not continuous tick drawdown. No live trades, no private raw data in GitHub, no PR merge.
