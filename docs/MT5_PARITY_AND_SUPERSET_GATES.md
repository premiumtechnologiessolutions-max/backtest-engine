# No Risk FX vs MetaTrader 5 Strategy Tester — Engineering acceptance gates

## No false claims

MetaTrader 5 already supports:
- every tick based on **actual broker-provided ticks**, generated tick simulation and M1 OHLC;
- Bid/Ask executions, variable historical spread, symbol settings and latency simulation;
- genetic / exhaustive optimization, forward tests, multi-symbol EA runs, local/remote/cloud agents;
- rich backtesting statistics including history quality.

See official MetaQuotes documentation:
- https://www.metatrader5.com/en/terminal/help/algotrading/testing
- https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation
- https://www.metatrader5.com/en/terminal/help/algotrading/strategy_optimization

**We cannot claim greater tick accuracy, speed or live-trading realism with only M1 OHLC.**
No Risk FX's attainable advantage is **auditable, reproducible strategy research,
cross-strategy portfolio modeling and leakage-resistant evaluation**, conditional
on actually implementing and verifying those features.

## Current repository status (October 25, 2026)

| Feature | Repository state | Acceptance before claim |
| --- | --- | --- |
| Yearly raw BID/ASK M1 importer | Implemented; 2012–2016 design and 2024 real-M1 samples audited, but original ZIP SHA not independently reverified in those runs | Full 2010–2026 import and original-archive SHA authentication remain acceptance gates |
| DST-aware gap catalogue | Implemented code, not certified | Reconcile against historical provider hours / broker metadata |
| M1 event engine | Reference, fast, Limit and unified shared-capacity replay locally tested; 263-test package suite passed at the recorded pre-tick-hardening checkpoint | Linux GitHub CI, additional broker-realism gates and regression after subsequent commits still required |
| All-in $0.40/oz round-trip | Implemented in M1 model | Zero movement must net -$0.40/oz and nothing additional charged |
| Weekly/monthly + marked equity | Implemented research reports | Verify against audited trade ledger, months crossing exits and floating risk |
| External Tick BID/ASK validator | Implemented in `ticks.py` | Source file plus provenance audit; still NO tick execution engine |
| Observed-tick order execution | **Not implemented** | Tick bid/ask event replay, stops, limits, ambiguous orders, verified broker rules |
| Broker parity regression vs MT5 | **Not implemented** | Identical broker quote feed, symbol settings, EA signal transcript, reconcile each fill |
| Multi-strategy concurrent portfolio | **Implemented for research**: shared Market/Limit positions, slots, ounces and marked/realized ledger; 2024 source-M1 acceptance passed | Real broker margin, correlated risk budgeting, quote-feed fills and liquidation rules not implemented |
| Purged Walk-Forward splits | Implemented planner, not experiment pipeline | Locked preprocessing, parameter selection on train only, embargo/purge validation |
| Robustness/FDR/Monte Carlo | **Not implemented** | Predefined analysis and deterministic result reproduction |
| Remote runner from ChatGPT | **Not implemented** | Secured authorized dispatch plus logged audited artifacts |
| CI in GitHub Actions | **Manual-only / no green runner evidence** under October 2026 quota blocker | Resume after quota reset, verify Linux Python 3.11 full suite and only then consider merging Draft PR |

## Three execution modes — mutually exclusive cost conventions

1. **M1 conservative synthetic-price research** (current): uses original BID-derived
   reference OHLC on both sides for the *research* P/L formula and subtracts the
   user's fixed **ALL-IN $0.40 per ounce** once per completed trade. Models
   same-minute SL-before-TP ambiguity and first observed quote after gaps, but
   CANNOT infer actual tick path.
2. **Observed tick research** (not yet implemented): independently obtained event
   timestamped Bid and Ask ticks with source, license, timezone, SHA-256 and
   quote-quality audit. Stop/limit trigger and quote side rules require detailed
   specification. For *fixed all-in* cost experiments, define a reference quote
   price convention so historical Bid/Ask spread is NOT charged a second time.
   Any broker-quote-execution scenario must separately report realized spread
   and MUST NOT silently add another fixed all-in fee.
3. **Broker-specific execution parity** (not yet implemented): requires real
   tick feed, XAUUSD symbol contract, execution/commission/slippage/swaps/margin,
   order types, fill policy, order rejection handling, server timezone and
   MT5 benchmark run. This is **a separate scenario**, not the user's primary
   $0.40 all-in research scenario.

The same run cannot report itself simultaneously as all-in fixed-cost research
and confirmed broker execution.

## Requirements before announcing 'stronger than MT5'

* All existing unit tests / CI **pass**, plus independent comparison fixtures.
* Tick replay is implemented and tested against a source-confirmed broker feed.
* At least 1000 deterministic event/quote/order scenarios for entry/cancel/
  partial fill/SL/TP/gap-through, with documented acceptance tolerances.
* 2010–2026 gold history reconciled, exceptional gaps source-checked or quarantined.
* Consistent weekly and monthly P/L by exit date, plus weekly/monthly equity
  mark-to-market and in-trade worst floating excursions.
* Multiple strategies simultaneously with **one** capital / margin / exposure
  ledger, synchronized signals and no hindsight portfolio weights.
* Reproducible experiment registry: repo revision, dataset SHA, strategy code hash,
  parameters, fee scenario, and outputs; previously exposed 2020–26 cannot be
  relabelled independent OOS.
* Strict walk-forward, Monte Carlo execution perturbations, parameter sensitivity,
  negative controls, multiple-testing adjustment and held-out forward tests.
* On a shared set of real ticks, compare MT5 native tester with our implementation;
  publish measured differences, NOT unsubstantiated speed/accuracy superiority.
* Only then can research depth and reliability be called stronger, supported
  by specific evidence. Profitable results or 81/81 months are NOT acceptance gates
  for data quality and are never guarantees of future returns.

## Developer-facing invocation

After installing `pip install -e ".[dev]"`, source audit:

```bash
norisk import-gold "/secure/Gold data.zip" --out data/processed
norisk audit-gaps --data data/processed --start 2010-01-01 --end 2026-09-20 --out reports/generated/gaps
norisk plan-walkforward --start-year 2012 --last-year 2024 --min-training-years 5 --embargo-days 14 --out reports/generated/folds.json
norisk audit-ticks --csv /secure/observed_tick_quotes.csv --provider "broker-provided source" --symbol XAUUSD --out reports/generated/tick-manifest.json
```

**Important:** `audit-ticks` checks the existence/schema/plausibility of
declared external ticks, and outputs `source_authentication: NOT_VERIFIED`.
It does not infer that a file originated from a broker, does NOT replay ticks,
and is not evidence of equality to the MT5 tester.


## Tick-to-M1 comparison: fail-closed audit inputs

The `compare_tick_bid_to_m1` helper now rejects NaN/infinite/negative
tolerances, invalid/nonfinite BID ticks, invalid/nonfinite M1 OHLC and
duplicate, unsorted or non-minute-aligned M1 timestamps. Previously a
`NaN` tolerance made every mismatch flag false, while Pandas
`max(skipna=True)` could hide a missing high/low among matching fields.
The timestamp-offset regex now uses a noncapturing group to avoid an
unnecessary Pandas capture warning.

Two regression tests were added to `tests/test_ticks.py`. The corrected
comparison logic passed 14 **isolated local cases** (including parameterized
negative cases) on Linux/Pandas; this was an extracted function harness, not
an execution of the full current GitHub checkout. The previously recorded
263-test source/wheel/sdist results predate these commits, so they must
not be presented as a full-suite pass for the new head. GitHub CI remains
unverified. This guard prevents false *audit* matches; it does not create
real tick data or broker execution parity.
