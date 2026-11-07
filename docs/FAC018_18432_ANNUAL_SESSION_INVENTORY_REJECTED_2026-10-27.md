# FAC018 — 18,432 official-source annual M1 executions, frozen hypothesis REJECTED (2026-10-27)

**Decision: REJECT.** No pre-registered joint acceptance passes. These are historically exposed **2012/2013** design years, not clean OOS. No live trading, tick/broker fill validation or monthly-profit guarantee.

## Immutable provenance and actual execution

- Frozen *before outcomes* at commit `dc7f3cac1bffca61546678e18bf6d79e397c11d8`: [FAC018 frozen specification](FAC018_FROZEN_SESSION_INVENTORY_H4_EFFICIENCY_2026-10-27.md). A single new **session-anchor inventory unwind / completed H4 efficiency** hypothesis family, with **9,216 correlated parameter specs** and only **144 pre-execution signal-rule combinations** (not thousands of independent hypotheses).
- Exact new code/tests commit `cb0c122c9573c22ad5b21bc1d101c541631ccb64` passed [CI 40472756466](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40472756466): **964/964 pytest** plus Python 3.12 compile/CLI checks. The CI verified-code artifact ID **12718772586**, SHA256 `f7283dfc0614e2083768477c81e9e37f2c1c8fa16d7d1b454a42c9bec6db7d0d`, was downloaded and executed locally. **No private quote data was uploaded to CI.**
- Original private `Gold data.zip` SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` verified locally before execution. Exactly **$0.40/oz ALL-IN roundtrip**, one ounce, one position, next eligible M1 open <=60s, stop-first, adverse gap-through, no fabricated minutes, UTC monthly exit-booked accounting, observed M1 floating equity.
- **2012:** 9,216 annual replays; **1,280 active** and 7,936 zero-trade; 110,592 monthly cells including zeros, 15,360 active cells. Maximum 9/12 positive months; maximum 39 fills/year; 19 unique signal streams including empty streams. Aggregate CSV SHA256 `c2ace7a900e2584b1a32fe4176ed0f8256eb09198190220bef902a627883124d`.
- **2013:** 9,216 annual replays; **1,280 active** and 7,936 zero-trade; 110,592 monthly cells including zeros, 15,360 active cells. Maximum 10/12 positive months; maximum 28 fills/year; 19 unique signal streams including empty streams. Aggregate CSV SHA256 `3d4bd29e2614cd34ca66fc54f87c1c7cf1564619d2f63bbe0a6288c8179e3db4`.
- Combined: **18,432 completed annual executions**, **2,560 active** and **15,872 zero-trade annual executions**; **7,808 specs zero in BOTH years**. **221,184** monthly cells including zeros; **30,720 active monthly values**. Highest **17/24** positive months; **0** at 24/24; **0** at >=18/24; **0** frozen joint acceptance passes; 253 specs positive annual net in both years, but NONE meet all gates.

## Risk-first exploratory diagnostics (NOT a validated winner)

Highest monthly count: `INV18_H04_K1.00_R0.25_TRANSITION_NY_LOCAL_0930_1330_SL2.25_TP0.50`. **7/12 in 2012, 10/12 in 2013, 17/24 total**; **29 and 26 fills**; 2012 **-$1.89125/oz**, 2013 **+$18.19125/oz**, combined **+$16.30/oz** *after* **$22.00/oz aggregate fees**. Worst UTC month **-$7.13/oz**; maximum annual observed M1 floating drawdown **$25.54375/oz**. REJECT: annual 2012 negative, both years below frozen >=100 fills/year, monthly count below >=18/24.

Highest aggregate net (a different, posthoc-picked configuration): **+$61.855/oz**, but only **13/24** positive months, 26 and 24 fills; worst month **-$15.055/oz**, maximum annual floating DD **$30.66/oz**. Also REJECT. This is *not* a superior accepted strategy.

## Canonical and independent reference parity

- **8** frozen-runner versus `run_fast` canonical full-year sample checks (4 per year): monthly net, fees, fills and M1 floating DD within 1e-7.
- **4 independent `execution.run` versus `run_fast` full-year exact checks**, two exploratory configurations in both years: **105 filled trades**, all 15 trade ledger fields, and **1,410,584 observed M1 floating-equity marks** matched with **maximum numerical difference 0**. These are engineering parity checks, not four independent market hypotheses.
- Local runtime Python 3.13.5; official GitHub CI Python 3.12.15. Frozen code artifact digest verified. Full parameter grid executed once per year; a separate 100-row 2012 smoke was not counted as an additional independent grid.

## Actual one-slot shared-capacity negative control (posthoc, not OOS)

For a diagnostic only, the two overlapping FAC018 variants with identical confirmations and SL2.25, but TP0.50 (priority first) versus TP2.25, were replayed **together in one account with one position**. The independently verified slow and fast portfolio ledgers/equity matched exactly over **705,292 M1 marks**.

| Year | Sum of standalone results — NOT executable | Actual one-slot shared result | Shared fills | Positive months |
| --- | ---: | ---: | ---: | ---: |
| 2012 | +$37.220/oz | **-$1.89125/oz** | 29 | 7/12 |
| 2013 | +$40.935/oz | **+$18.19125/oz** | 26 | 10/12 |
| Combined | **+$78.155/oz** | **+$16.300/oz** | **55**, versus 105 standalone fills | **17/24** |

Shared portfolio worst month **-$7.13/oz**, max annual floating DD **$25.54375/oz**, fees **$22/oz**. The $61.855 difference demonstrates why summing overlapping standalone P/L is invalid. Components were selected after viewing exposed design outcomes: **this is a negative-control engineering demonstration, NOT prospective portfolio validation**.

## Research disposition

No thresholds are retuned and no rejected candidate is promoted. The batch is **closed as rejected**. Before any prospective test, select a *new* immutable rule with embargo and multiple-testing controls, and collect genuinely unseen forward observations. Tick BID/ASK, spread, slippage, broker constraints, and capacity outside this synthetic one-slot model remain unverified. PR #1 stays Draft/unmerged; no billing/privacy changes or live orders. Private original ZIP, raw BID/ASK and individual quote/trade ledgers remain outside the public repository.
