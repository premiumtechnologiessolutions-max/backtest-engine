# Original authorized Gold ZIP — frozen BOS/H1 source replay and archived-ledger parity

**Date:** 2026-10-27 UTC. **Exact code artifact/CI commit:** `f6d625cdef6dcccfdce379fd72b2d1865e41068a`.

## Provenance and limits

- Authorized original private `Gold data.zip` was accessed **locally**, not committed or uploaded to GitHub. Verified SHA256: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
- Code came from the GitHub Actions verified-code artifact for the exact commit above. Its ZIP SHA256: `3d472b522dc4d257a189ef6837dfa442b74e86847275056cd58dbed9eea3960f`.
- Independent *archived earlier local run* ledger source: `NoRiskFX_Quant_LongSession_Safety_Audit_2026-10-25.zip`, SHA256 `c64937e16caa793866bacf49c7b24d48bb038d6706890775795a0c0dfb0c1c7c`. **This is not an independent broker or market-data provider** and is not clean OOS.
- Official runner: `scripts/run_bos_fib_frozen_sensitivity.py`, actual package strategy/filter/execution/report stack, fixed `$0.40/oz` all-in roundtrip cost, one ounce.
- Four **separate, successful single-year runner commands**, with source-hash verification and reconciled monthly/weekly reports. An additional combined 2017+2020+2024 command **timed out**; it is **not** counted as a successful aggregate command.
- Archived and new `trades.csv` files matched **all 15 common fields** for each corresponding trade, in original row order: 5 text/UTC timestamps exact, 2 discrete fields exact, and 8 numeric fields with absolute tolerance `1e-10` and zero relative tolerance. New-only diagnostic fields were not part of this historical comparison.

| Year | Source M1 rows | Trades matched | Positive months | Net USD / 1 oz | Fees USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2012 | 352,975 | 668 | 0/12 | -242.85294 | 267.20 |
| 2017 | 352,785 | 282 | 0/12 | -129.69146 | 112.80 |
| 2020 | 355,432 | 929 | 0/12 | -387.98588 | 371.60 |
| 2024 | 355,893 | 997 | 0/12 | -465.69532 | 398.80 |
| **Total of separately executed years** | — | **2,876** | **0/48** | **-1,226.22560** | **1,150.40** |

For every year, the report's monthly and weekly net P/L reconciled to executed trades and fees reconciled to `0.40 × number_of_trades`. These are **four separate calendar-year experiments, not one continuous portfolio**.

## CI and decision

[GitHub Actions run 40531528349](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40531528349) **passed on exact commit**: Python 3.12.15, constrained install, dependency check, compilation, **1,138 pytest tests passed**, CLI smoke and 26-trade synthetic reference/fast parity.

**Decision: REJECT the frozen BOS/H1 strategy** (zero positive months after fixed costs in these exposed years). This historical replay demonstrates reproducibility, **not** forward performance, clean OOS, real BID/ASK tick fills, slippage, margin feasibility, or monthly profitability.

Keep PR #1 **Draft/unmerged** until separately preregistered untouched OOS research and broker execution gates. GitHub reports repository visibility as **public**, despite the intended private status; no private market data or trade-level ledgers are committed.
