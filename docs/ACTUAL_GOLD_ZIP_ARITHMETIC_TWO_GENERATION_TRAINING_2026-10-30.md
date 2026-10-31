# Original Gold ZIP: 2 generations of arithmetic research on exposed 2012–2013 training (2026-10-30)

## What actually executed

For the first time in this series, the complete `scripts.run_arithmetic_research_cycles` loop was executed against the **authorized original local** `Gold data.zip` (155,808,257 bytes; SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`). The raw ZIP, M1 BID/ASK rows, all detailed trades, equity marks, and source-derived reports **remained local/private** and were **not pushed to GitHub**.

The source code was recovered from the GitHub Actions verified-code artifact. Critical local source files (orchestrator, annual replay, CLI, formula engine, integration test) had blob SHA identities matching the corresponding files on the GitHub branch at verification. Full CI on the code branch also passed 3,051 tests in [run 41056118093](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41056118093). This historical data run is not a complete independent source-tree audit or broker tick-fill replay.

**Sequence:** 10 previously studied, historical-training candidates were converted from the private 2012–2013 training proof into the canonical frozen input; a single new formula was generated at each of generations 1 and 2; each was executed **separately for both full years** with canonical Reference and Fast M1 execution, 1 oz, **$0.40/oz all-in cost**. Each annual shard passed 15-field trade parity, monthly/weekly, observed-minute equity, fee/source fingerprints, and provenance gates; `compile_feedback` produced immutable inputs for the next generations. Re-running generation 1 used frozen, verified existing annual shards instead of re-running them.

## Verified annual training results

| Generation | Year | Trades | Net USD/oz | Profitable months | Fees USD |
|---|---:|---:|---:|---:|---:|
| 1 | 2012 | 521 | -237.71 | 4/12 | 208.40 |
| 1 | 2013 | 617 | +354.54 | 7/12 | 246.80 |
| 2 | 2012 | 510 | -362.80 | 2/12 | 204.00 |
| 2 | 2013 | 611 | +405.69 | 8/12 | 244.40 |

Annual tests are **separate historical training runs**, not one continuous compounding portfolio.

- **Generation 1:** 1,138 trades; net +116.83 USD/oz; 11/24 profitable months; total fees 455.20 USD; formula identity `ea37e9ddbe8ec8e0fd9c30ee1de39071c809c30805cbdcf5cc64afd7f0868a44`.
- **Generation 2:** 1,121 trades; net +42.89 USD/oz; 10/24 profitable months; total fees 448.40 USD; formula identity `9ee969cb324b24a9ac4ecd88d6f013680daf9485eaa10cb413095011756a4e52`.

Two audited formula-year pairs per generation, with immutable next input SHA256:

- Generation 1: `3f9ffbd742e07b12b922e23ce3614de7b9e4ba14308c5ab22b303ffe23177179`.
- Generation 2: `6900758c720521077cd3f98f06e7712dcaf79b323924eb33e88bdd570af7e24c`.

The BID/ASK M1 fingerprints were identical across the two formula generations for each respective source year and reconciled with the historical source ledger.

## Research conclusion and gates

**Engineering milestone: one actual, audited two-generation training loop completed.** This closes the prior gap between isolated pieces of the software and a working end-to-end research cycle on real source data.

**No trading edge is proven.** The years were exposed and repeatedly studied before this test, therefore they are **NOT** fresh OOS. Both formulas lost money in 2012 and neither satisfies the goal of positive results every month. Synthetic common-BID M1 fills, no real broker tick/latency/margin model; no live-trading authorization. Continue to keep PR #1 Draft and unmerged until a prospective freeze and true independent validation are completed. No private data, billing, or GitHub visibility changes.
