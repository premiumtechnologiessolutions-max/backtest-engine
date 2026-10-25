# M1 BOS/Fibonacci + confirmed H1 regime — frozen study (2026-10-25)

**Research decision: REJECT both tested variants. Not a live trading system; no monthly profit guarantee.**

## Causal specification, predeclared before evaluation

- Original source: private XAUUSD `Gold data.zip` source SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Do not commit raw market data.
- Base M1: confirmed 3-left/3-right pivot swings, directional BOS on closed M1, Fib 0.618 Golden Zone limit pullback, swing SL plus $0.10, 1R TP, 120-minute order expiry, first two BOS regime events.
- H1 gate: only 60-of-60 observed M1 candles in UTC hour. Buy if last COMPLETED H1 close > EMA50 AND EMA50 > its value 5 **completed** H1 candles prior; reverse for sell. Match only status known by M1 signal confirmation time (not latest hindsight H1).
- Frozen candidates: `h1_only` and `h1_and_5x`; latter additionally requires entry-to-TP planned price movement >= **$2.00/oz**, or 5× a fixed **ALL-IN $0.40/oz round-trip research fee**. No additional variable spread or commission. Reference BID OHLC, same-minute stop first, same-minute entry TP deferred when price order unknown.
- Strict train window **2012–2016**, chronological check **2017–2019**. Prior project saw portions of those historical periods, so do not call it a truly independent prospective OOS. The variants failed these periods, so **no selection using previously exposed 2020–26** was done.

## Execution results — local standalone M1 research runner (USD for 1 oz)

| Period | Model | Executed trades | Positive months | Net USD | Worst month |
| --- | --- | ---: | ---: | ---: | ---: |
| 2012–2016 design | H1 only | 2,784 | 0/60 | -1,133.61 | -43.17 |
| 2012–2016 design | H1 + fee 5× | 42 | 5/60 | -24.88 | -7.52 |
| 2017–2019 chronological | H1 only | 970 | 0/36 | -440.20 | -36.54 |
| 2017–2019 chronological | H1 + fee 5× | 4 | 1/36 | -5.85 | -2.78 |

All 16 year × candidate ledgers reconciled to weekly and monthly P/L and every completed 1oz trade was charged exactly $0.40. Independent local strategy and H1 quality-gate unit tests: **8/8 passed**.

## What is actually in GitHub

- `src/norisk_quant/h1_regime.py`: deterministic H1 60/60 candles, 50-EMA / 5 H1-bar trend slope, last-confirmed-only filtering.
- `src/norisk_quant/cli.py`: `--strategy bos-fib --timeframe M1 --bos-require-h1-trend` and optional `--bos-min-gross-reward-fee-multiple 5`.
- `tests/test_h1_regime.py`: source completeness, no-lookahead, H1 warmup and signal-order timing.
- Full 2012–2019 source-independent standalone reproduction and all monthly/weekly/trade CSVs in the conversation archive `NoRiskFX_BOS_Fib_H1_Regime_Frozen_Audit_2012_2019.zip`, including `run_h1_frozen.py`, `frozen_spec.json`, `audit.json`, `period_results.csv`, and `RESEARCH_REPORT_AR.md`. ZIP does NOT include raw market data.

## Limits and gate before acceptance

These runs used a **local standalone replay**, not executing the connected GitHub package's entire `run_limits` and reporting pipeline with certified trade-by-trade parity. H1 EMA warmup restarts annually; all years are separately executed, not one continuous cross-year account/margin portfolio. M1 candle high/low does not reveal intra-candle event order. GitHub Actions is temporarily manual-only due to exhausted private account October allowance; no passing CI has been demonstrated, and draft PR #1 must not merge until independent tests and exact real-data fill parity pass. No model in this analysis satisfies the user's steady-monthly-profit objective.

**Research decision:** do not retune EMA, cost multiple, Fibonacci percentage or time windows against exposed results to manufacture a favorable month count. Better next hypothesis must be genuinely distinct market structure/microstructure with frozen ex-ante rules.
