# Negative-control study: daily quote-reopen gap reversal — 2026-10-25

**Decision: REJECT**, without inspecting 2017–2026 outcomes for parameter selection.

## Fixed hypothesis before observing results

The research study was written and hashed before backtesting: Python source SHA-256
`75a9ba10d56ce62d2beebbd0c5eb9441d5ad89efe8ba0d3f09d4b4c97c75aef0`.

- XAUUSD original private M1 Bid/Ask annual ZIP SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`; never uploaded to GitHub.
- Detect **30–180 missing M1 minutes**, then a first observed reopening quote differing from the last pre-gap close by ≥**0.15%**.
- Observe the full **first reopening minute**, then enter **against the gap** at the **next contiguous M1 opening** only if price still offers a target on the correct side.
- Target the last close before the gap; stop one original gap magnitude beyond reopening price; exit at first observed M1 open after **90 elapsed minutes** if no SL or TP. Stop-first when both levels occur in one M1 bar; worsening stop gap-through fill uses first observed open.
- Charge **$0.40 all-in USD per 1oz full roundtrip** exactly once. No other spread/commission/slippage, no actual Bid/Ask tick-fill claim.
- Yearly P/L assigned to trade exit UTC month. Samples are **separate annual runs**, not one multi-year portfolio. Original hypothesis is a quote-gap pattern; data alone cannot authenticate *why* a price feed paused.

## Completed training results 2012–2016

| Year | Trades | Positive months /12 | Net P/L USD per 1oz |
|---|---:|---:|---:|
| 2012 | 1 | 1 | +2.02 |
| 2013 | 10 | 3 | -6.08 |
| 2014 | 10 | 6 | +10.27 |
| 2015 | 6 | 0 | -3.12 |
| 2016 | 5 | 0 | -4.43 |
| **Total** | **32** | **10/60** | **-1.34** |

Gross price P/L **+$11.46**, total all-in cost **$12.80**, net **-$1.34**. Exit reasons: **19 timed**, **9 target**, **4 stop**. Trade, weekly, monthly and annual realized P/L reconciled; $0.40 per closed trade. The sample is very small and overall negative; **no validation-stage trial was justified**.

Reopen hour (UTC) counts from observed trades: **22h:23**, **23h:6**, **02h:1**, **16h:1**, **17h:1**. That three of 32 qualifying feed gaps fell outside the common 22/23 UTC pattern is an additional reason to avoid claiming these are verified broker daily-market closures. Missing M1 quotes do not prove an exchange/broker holiday or closure.

## Evidence / scope

The reproducible local source, frozen source SHA, full trade ledgers, weekly/monthly CSVs for all five training years, summary and audit live in the user's conversation file **`NoRiskFX_Frozen_Daily_Gap_Negative_Control_2012_2016.zip`**, without the licensed original source ZIP. This was executed as a standalone research script and **not** certified central GitHub package/CLI execution. These years were also touched by previous research and are not clean prospective OOS.

**Next engine research gate:** complete GitHub package tests and actual-parity verification, then pre-register genuinely independent liquidity hypotheses before evaluating any new candidate. Do NOT retune this gap setup against the previously exposed 2017–2026 years or claim steady monthly profitability.
