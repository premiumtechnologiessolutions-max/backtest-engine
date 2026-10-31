# M1 BOS + Fibonacci Golden Zone — fixed variants audit (2026-10-25)

**Status:** RESEARCH / REJECT the tested variants for monthly-profit goals. These are NOT all conceivable BOS/Fibonacci strategies, NOT authentic broker fills, and NOT a clean prospective OOS trial.

## Source and fixed contract

- Original private XAUUSD M1 Bid/Ask annual JSON archive (2010–Sep2026), SHA256: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`; original raw ZIP remains **outside GitHub**.
- Chart premise from user image: M1 trend, confirmed break of structure, Fibonacci retracement into Golden Zone (0.618–0.786), avoid chasing, SL beyond swing, TP 1R or 1.5R, first/second wave only.
- Mechanical definitions: a pivot is confirmed after 3 additional M1 closes (3 bars left and right); trend needs rising/falling *two* confirmed pivot highs and lows; BOS needs close $0.10 beyond latest opposite structure, with opposite anchor swing after that broken pivot. Same-trend BOS event count limited to 2 per regime; **mechanical two-event proxy**, not discretionary Elliott wave count.
- Fibonacci impulse is latest confirmed opposite anchor to highest/lowest price up to completed BOS minute. Limit order is placed after BOS candle close at retracement 0.618 (comparison 0.705); protective stop $0.10 beyond anchor, expiry after 120 elapsed minutes. A setup crossing an unobserved price gap is rejected.
- One simulated position at a time. Historical synthetic BID-reference OHLC Limit fills; stop-first where M1 intrabar order is unknowable; gap-through stop at first observed opening price. **Only fixed ALL-IN $0.40 per ounce per completed trade**, no separate variable spread/commission/slippage.
- Frozen three variants: `fib618_R1`, `fib705_R1`, `fib618_R1p5`, with identical swing/BOS confirmations.

## Standalone real-data replay — calendar-year runs, 1 oz

| Year | Variant | Orders | Executed trades | Net USD | Positive months / 12 |
|---|---|---:|---:|---:|---:|
| 2012 | fib618_R1 | 2,127 | 1,617 | -405.97 | 0 |
| 2012 | fib705_R1 | 2,127 | 1,538 | -336.09 | 0 |
| 2012 | fib618_R1p5 | 2,127 | 1,613 | -533.81 | 0 |
| 2017 | fib618_R1 | 879 | 647 | -259.93 | 0 |
| 2017 | fib705_R1 | 879 | 611 | -209.61 | 0 |
| 2017 | fib618_R1p5 | 879 | 647 | -271.00 | 0 |
| 2020 | fib618_R1 | 2,836 | 2,149 | -504.27 | 0 |
| 2020 | fib705_R1 | 2,836 | 2,070 | -426.34 | 0 |
| 2020 | fib618_R1p5 | 2,836 | 2,142 | -757.24 | 0 |
| 2024 | fib618_R1 | 3,074 | 2,284 | -597.29 | 0 |
| 2024 | fib705_R1 | 3,074 | 2,171 | -485.77 | 0 |
| 2024 | fib618_R1p5 | 3,074 | 2,279 | -872.07 | 0 |

### Why 2024 net is negative even with positive gross

Base fib618_R1 had approximately **+$316.31** gross price P/L, but **$913.60** all-in charges (2284 trades × $0.40/oz), leaving **-$597.29** net. fib705_R1 had +$382.63 gross and $868.40 charges, net -$485.77. A nominal winning percentage does not imply net edge.

## Verification state

1. New `src/norisk_quant/bos_fib.py` + `tests/test_bos_fib.py` were pushed to the development PR. Five causal/lookahead/gap/fibonacci parameter synthetic tests **passed in a local minimal package scaffold**; complete repository suite and exact GitHub `run_limits` integration tests are **not certified** (Actions quota was exhausted until Nov 1).
2. The real-year numbers come from a **standalone limit replay** matching the FVG standalone order-event conventions, NOT from executing the actual central GitHub package. Whole-repo execution parity by matching every trade's timestamp, price and exit reason still remains.
3. Each year was executed individually; year-end closing could create a synthetic end-of-data liquidation. These cannot be read as a single continuous 2012–2024 portfolio or as clean untouched OOS.
4. The past 2012, 2017, 2020, 2024 periods have already been explored in broader historical research. There is **no guaranteed profitable month** and no proof of superior broker fill accuracy versus MT5.
5. Local checkpoint `NoRiskFX_BOS_Fibonacci_M1_2026-10-25_Research.zip` in the conversation has executable standalone script, synthetic tests, per-trade CSV, per-week/per-month CSV and daily M1-marked-equity samples for all 12 year/variant runs. Raw Gold data ZIP excluded.

**Research decision:** The exact pictured-rules machine interpretation is unqualified. Next hypothesis should specifically reduce excessive low-R/$0.40 cost burden *without hindsight selection on 2024*, by preregistering cost-to-risk or regime filters using pre-2020 training only, then doing walk-forward checks.
