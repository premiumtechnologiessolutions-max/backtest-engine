# XAUUSD M1 Bid/Ask ingestion integrity — 2026-10-26

## Scope
This is a source-validation hardening change, **not** a new strategy or backtest.
Changes are in `src/norisk_quant/data.py` and `tests/test_ingest_quote_integrity.py`.

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
- Two commits saved to the development branch: code `49a205e`,
  regression tests `3658734`.
- A separate local six-fixture check of the new finite/positive/crossed
  high-low predicates passed (6/6). This is **not** the repository test suite.
- New GitHub pytest cases were added, but **not executed here** against
  the full installed repository. The local runtime lacks `pyarrow` and
  cannot fetch the private repository over the network.
- No GitHub Actions success is claimed. The existing CI quota blocker
  remains unresolved. Keep Draft PR #1 unmerged.
- No raw Gold data ZIP, annual JSON, tick feed or live-trading credentials
  were uploaded.

## Next gate
Run the current complete installed-package tests and verify imported Parquet
partitions receive equivalent fail-closed validation on reload. Replay the
pre-existing 13-field execution parity against the exact original private
archive only in a runtime where that archive is actually available. Do not
rerun completed strategy profitability searches merely to test this change.
