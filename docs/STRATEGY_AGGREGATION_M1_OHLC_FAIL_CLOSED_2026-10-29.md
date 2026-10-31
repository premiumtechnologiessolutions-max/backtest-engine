# Direct strategy M1 OHLC fail-closed contract (2026-10-29)

Scope: `aggregate_bars` used by EMA, Donchian and liquidity-sweep research strategies.

Previously the public strategy API checked missing values and M1 timestamps but did not independently reject nonfinite positive-infinity values, negative prices, string/bool OHLC, or geometrically impossible candles (high below open/close; low above open/close). The canonical source importer performs stronger validation, but callers may construct DataFrames directly and bypass ingestion. Malformed input must never create a seemingly complete higher-timeframe signal.

The function now checks the four OHLC columns for numeric nonboolean dtype, finite strictly positive prices and consistent high/low/open/close geometry *before* M1 or higher-timeframe aggregation. This does not change strategy parameters, transaction costs or validated clean-data outcomes.

`tests/test_aggregate_ohlc_geometry.py` includes 14 negative M1/M15 cases, a positive complete M15 case and empty-data case. A reconstructed older repository snapshot (not this GitHub HEAD) passed 59 scoped tests and 566 non-Parquet tests with the same patch. Eight unrelated local tests require unavailable `pyarrow` and were not counted as passing. GitHub CI on the new commit must be checked separately.

This is engineering safety, not a market backtest, 13-field original Gold ZIP replay, broker tick-fill validation, OOS evidence, or profitable strategy discovery. No raw quote data is published. Keep PR #1 Draft.
