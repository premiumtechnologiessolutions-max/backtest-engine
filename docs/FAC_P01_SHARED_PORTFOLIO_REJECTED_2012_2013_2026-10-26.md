# NRF-FAC-P01 — fixed shared-capacity Donchian + wick negative control

**Frozen before original-data results** at commit `849f6fd05e356769f2dfb8d80de4d355761250dc`: `docs/FAC_P01_FROZEN_SHARED_PORTFOLIO_NEGATIVE_CONTROL_2026-10-26.md`. Two arbitrary, not winner-selected, fixed entry specifications: Donchian M15 lookback 10, SL $5, TP $10; wick rejection M15 ratio 1.50, min range $3, SL $5, TP $10. Wick-first on equal signal timestamp. No live trades, no post hoc tuning.

**Source:** private original XAUUSD BID/ASK M1 ZIP SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`, 2012 and 2013, one ounce, one **shared** position, next observed M1 open ≤1 min after full M15 close, stop-first, adverse gap-through, $0.40/oz all-in full roundtrip. Separate annual year-end closes.

## Results (USD per 1 ounce, after costs)

| Year | Strategy | Trades | Net USD/oz | Fees USD/oz | Positive months | Max M1 floating DD USD/oz |
|---|---|---:|---:|---:|---:|---:|
| 2012 | Wick only | 346 | -257.96 | 138.40 | 3/12 | 293.90 |
| 2012 | Donchian only | 785 | -397.38 | 314.00 | 3/12 | 429.17 |
| 2012 | **One-position shared** | **845** | **-401.18** | **338.00** | **2/12** | **410.88** |
| 2013 | Wick only | 433 | +50.88 | 173.20 | 8/12 | 190.21 |
| 2013 | Donchian only | 878 | -511.64 | 351.20 | 1/12 | 574.93 |
| 2013 | **One-position shared** | **975** | **-485.34** | **390.00** | **2/12** | **553.95** |

Naive arithmetic of **separately executed** ledgers (not a portfolio): 2012 **-$655.34** vs actual shared **-$401.18**; 2013 **-$460.76** vs actual shared **-$485.34**. This demonstrates why adding independent backtest profits is mathematically invalid when entries compete for one position capacity.

**Strong validation:** Both shared-capacity runs were independently re-executed with the **reference `norisk_quant.execution.run`** against `norisk_quant.fast_engine.run_fast` on the same original private M1 bars and same ordered signal list. All **845 (2012) and 975 (2013) individual trade ledger rows** matched (entry, exit, side, fees, net, reasons) and **every one of 352,975 + 352,317 = 705,292 observed M1 equity marks** matched to tolerance 1e-8. Exact net P/L deltas 0.0. Source data were never uploaded.

**Decision: REJECT P01.** Portfolio loses in both exposed historical years, with only 2/12 positive months each. It is a capacity-correct negative control, not a candidate to optimize or deploy. Monthly CSV, yearly summary and full reference parity JSON are retained in private research results archive `NoRiskFX_FAC002_FAC003_2026-10-26_Verified_Research.zip`. No clean OOS, no broker tick fill claim, no guarantee.
