# FAC026 source-year/calendar/epoch preflight — 2026-10-30

## Scope and frozen research status

This change hardens the **already rejected** FAC026 source reader; it does **not** introduce a new hypothesis, alter any of its 32 correlated frozen settings, run new source-data backtests, or reopen FAC026 for optimization. Its historically exposed 2012/2013 structural result remains **18 distinct candidate timestamps**, with **13/24 months having no structural candidate** across the frozen variants.

Before constructing M15/H1 candles, `load_year` now fails closed if the JSON source member has an empty timestamp series, a non-integer epoch (including fractional, string or null), an out-of-year UTC timestamp, or fewer than all twelve distinct UTC calendar months. It still enforces ordered, unique, minute-aligned timestamps, valid positive BID/ASK OHLC and paired ordering. The year check is based on UTC instants, not host timezone or file names.

Seven new synthetic regression cases cover a valid 12-month member, a missing month, a wrong-year member, three non-integer epoch representations, and an empty member. These tiny fixtures are **not** evidence of complete observed market minutes or realistic weekend/holiday closures; existing complete-candle guards remain essential. Source ZIP SHA256 is still checked before opening the archive.

## Provenance / results

- Source module: `scripts/research_fac026_original_source_structural.py`
- Synthetic tests: `tests/test_research_fac026_original_source_structural.py`
- Private Gold ZIP: **not read or uploaded by this change**.
- New source strategy backtests: **0**.
- New monthly P/L / worst month / floating M1 drawdown: **N/A**.
- New independently accepted hypotheses / strategies: **0 / 0**.
- Fee contract remains **exactly $0.40/oz ALL-IN roundtrip**; no live execution.
- Exact executable-code head `a34f45ff6c282d835c3ae0df588cec2a01437030`: [Engine quality gates 41032154851](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41032154851) **SUCCESS — 2,978 pytest passed, 1 warning**; [Quant Lab 41032163081](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41032163081) **SUCCESS**. Metadata-only follow-up commits require their own exact-head CI check.
- PR #1 must remain **Draft, unmerged**; public repository must not contain raw quotes.

This is a necessary calendar-integrity gate, not a complete missing-minute audit, broker BID/ASK fill proof, canonical parity replay, embargoed prospective OOS evaluation or a profitability result.
