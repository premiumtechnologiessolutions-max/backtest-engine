# XAUUSD M1 Bid/Ask ingestion integrity — 2026-10-26

## Scope
This is a source-validation hardening change, **not** a new strategy or backtest.
Changes are in `src/norisk_quant/data.py` and `tests/test_ingest_quote_integrity.py`. The final load path now also revalidates cached Parquet, preventing a changed partition from bypassing the original ZIP manifest.

Previously `normalize(strict=False)` could feed a ZIP manifest acceptance
decision using only OHLC bounds and opening/closing BID/ASK checks. A missing,
infinite, zero or negative price could evade that acceptance predicate, and
crossed high/low quotes were not explicitly checked. In the strict direct-ZIP
path, minute-open alignment was also not enforced by `normalize`.

## Current acceptance gates
- Every BID/ASK OHLC price is finite and strictly positive.
- Each side has internally valid open/high/low/close.
- ASK open/high/low/close must not be below the corresponding BID field.
- Strict source timestamps are valid UTC minute opens.
- Annual import records `nonfinite_price_rows`, `nonpositive_price_rows`,
  `ask_below_bid_high`, and `ask_below_bid_low` in the manifest and
  quarantines an annual partition if any are nonzero.
- The importer still does not interpolate, replace or conceal bad quotes.

These checks do not establish tick chronology, executable broker spreads,
fill accuracy, or an independent data source. The canonical research cost
remains fixed **$0.40/oz ALL-IN per completed round trip**.

## Verification status
- Four implementation/test commits saved to the development branch: `49a205e`, `3658734`, `8c9a429`, `fdfaaa2`. The last two add cached-Parquet revalidation and regression coverage.
- Separate local reconstructed checks passed: 6/6 quote-predicate fixtures and 6/6 cached-M1 validation fixtures. These are **not** the repository test suite or a run of the exact installed package.
- New GitHub pytest cases were added, but **not executed here** against
  the full installed repository. The local runtime lacks `pyarrow` and
  cannot fetch the private repository over the network.
- No GitHub Actions success is claimed. The existing CI quota blocker
  remains unresolved. Keep Draft PR #1 unmerged.
- No raw Gold data ZIP, annual JSON, tick feed or live-trading credentials
  were uploaded.

## Next gate
Run the current complete installed-package tests and run the newly added cached-Parquet tests with `pyarrow`. Audit whether the original Gold archive itself meets the stricter high/low quote invariants before interpreting any resulting import rejection. Replay the
pre-existing 13-field execution parity against the exact original private
archive only in a runtime where that archive is actually available. Do not
rerun completed strategy profitability searches merely to test this change.


## Additional direct-Parquet ingress gate (2026-10-26)
A separate public API path, `read_source("file.parquet")`, previously
returned a cached DataFrame immediately when it already had a DatetimeIndex.
That bypassed `validate_loaded_m1` even though `load_market` applied the
gate after date slicing. Downstream users calling `read_source` directly
could therefore receive nonfinite, crossed, off-minute or non-UTC quotes.

`read_source` now calls `validate_loaded_m1` before returning a Parquet
DataFrame with a DatetimeIndex. This is fail-closed, preserves valid source
rows, does not change the $0.40/oz ALL-IN research cost, and does not create
synthetic missing minutes.

Regression file: `tests/test_read_source_parquet_gate.py` (one valid case
and six malformed cases). A **separate isolated local reproduction** of the
same guard passed 6/6 fixtures with a mocked Parquet reader. The new GitHub
test file and the complete installed repository suite **have not yet been
executed in this runtime**; `pyarrow` and authenticated network clone are
not available. This is not CI success or real-source parity evidence.
