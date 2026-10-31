# XAUUSD M1 BOS/Fibonacci — conservative same-entry target and pre-trade cost filters (25 Oct 2026)

**Research status: REJECT 0x/5x/10x tested variants. Do not deploy; not evidence of clean OOS or executable tick fills.**

## Why prior numbers were revised

The old M1 OHLC limit-entry replay allowed a take-profit in the **same 1-minute candle** in which a pending Limit order became filled. That candle's high/low does not tell us whether target preceded the fill, so this is an optimistic and potentially impossible win. Corrected conservative rule:

- SL hit in the entry candle: assume SL first (same prior convention).
- TP hit in entry candle with no SL: **do not award TP**. Keep the position and test stops/targets from the **next observed M1 candle**, including adverse gap-through prices.
- Annotate `Result.uncertain_entry_tp_deferred`; export to `summary.json` as `same_entry_bar_target_deferred`.
- This is an intentionally conservative scenario, not reconstruction of actual tick ordering.

Implementation: `src/norisk_quant/limit_engine.py`; dataclass `src/norisk_quant/execution.py`; reporting `src/norisk_quant/report.py`; regression fixtures `tests/test_limit_execution.py`.

## Frozen cost-screen hypothesis

Same M1 causal confirmed swing/BOS, Fib0.618, first two regime BOS events, SL at swing with 0.10 USD buffer, 1R TP, expiry120m and all-in **$0.40/oz roundtrip**. Three settings (selected before the research sweep): **0x** unfiltered, **5x** projected gross TP distance ≥ $2.00/oz, **10x** ≥ $4.00/oz. Threshold uses only the known intended entry and target at signal time, not subsequent outcomes. Source function `bos_fib_limit_orders` exposes `min_gross_reward_fee_multiple` and `all_in_cost_per_ounce`; CLI `--bos-min-gross-reward-fee-multiple`.

### Full original gold M1 historical replay (standalone, not certified repo parity)

| Period | Filter | Positive months | Trades | Net USD/oz | Worst month |
| --- | --- | ---: | ---: | ---: | ---: |
| 2012–2016 design | 0x | 0/60 | 6,334 | -2,582.96 | -81.70 |
| 2012–2016 design | 5x | 13/60 | 109 | -57.03 | -11.72 |
| 2012–2016 design | 10x | 3/60 | 10 | -9.23 | -8.37 |
| 2017–2019 chronological check | 0x | 0/36 | 2,228 | -988.54 | -81.11 |
| 2017–2019 chronological check | 5x | 7/36 | 19 | +2.96 | -3.33 |
| 2017–2019 chronological check | 10x | 0/36 | 0 | 0.00 | 0.00 |
| 2020–Sep 2026 historically EXPOSED | 0x | 0/81 | 14,606 | -6,594.43 | -215.75 |
| 2020–Sep 2026 historically EXPOSED | 5x | 20/81 | 2,476 | -1,236.98 | -163.26 |
| 2020–Sep 2026 historically EXPOSED | 10x | 12/81 | 543 | -286.12 | -101.75 |

The apparent +$2.96 in 2017–19 (5x) consists of **19 trades in 36 months** and is **not meaningful independent validation**. 2020–26 was already examined in previous research and is **not fresh held-out testing**; Sep 2026 is incomplete. Years were replayed separately; 0 forced end-of-data exits were seen in this sweep but it is not a 15-year continuous portfolio-capital replay.

### Concrete effect of fixed fill chronology

| Year | Old BOS fib618/1R net | New conservative net | Same-entry-bar TP deferred |
| --- | ---: | ---: | ---: |
| 2012 | -405.97 | -637.48 | 354 |
| 2017 | -259.93 | -289.15 | 64 |
| 2020 | -504.27 | -942.21 | 527 |
| 2024 | -597.29 | -1,020.33 | 503 |

For precise unrounded year/variant results, use the archived yearly/monthly ledgers, not the rounded table. The correction does not create a deployable edge.

## Independent effect check on an older FVG 2024 variant

A standalone rerun of 871 H1 three-candle FVG midpoint orders under the same conservative target deferral produced **357 completed trades**, **one** deferred same-entry target, **-925.325 USD/oz net**, and **3/12** positive months. Net is unchanged to displayed precision versus the old standalone replay. This result pertains to **that FVG H1 2024 fixture**, not all FVG variants or 2012–26.

## Evidence and limitations

- Original private `Gold data.zip` source SHA-256: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`; never commit raw licensed data.
- The current conversation artifact is `NoRiskFX_BOS_Fib_Cost_Gate_Conservative_Replay_2012_2026.zip`: standalone source, tests, 45 annual trade ledgers, aggregated 177 monthly points **per model**, weekly files, period summary, FVG 2024 sensitivity comparison and source hashes.
- Across 45 annual BOS runs, individual trade ledgers agreed with their monthly/weekly totals and final sampled equity at ≤$0.000001. The script checks all fees are $0.40 per completed 1oz trade.
- OHLC backtesting cannot know intraminute event ordering. Conservative fill assumptions must not be advertised as real tick execution.
- **GitHub central-engine pytest + exact trade-by-trade parity is still not certified**, since Actions runners were blocked after the GitHub account exhausted its monthly 2,000min/0.5GB quota. Draft PR #1 must remain unmerged pending proper tests.
- The cost-screen is an ablation study, **not a newly discovered profitable strategy**. Avoid weighting any unqualified results into a portfolio or claiming that it will earn money every month.

Next: verify GitHub package locally or on a runner, then pursue an **independent and pre-registered** change to the entry *quality* (higher-TF regime, multi-timeframe structure, or other genuinely different signal) rather than posthoc tweaks to the fixed cost threshold.
