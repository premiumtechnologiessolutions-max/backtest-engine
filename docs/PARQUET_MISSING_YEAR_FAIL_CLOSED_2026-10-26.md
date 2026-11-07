# Parquet annual-coverage fail-closed gate — 2026-10-26

## Finding

Direct ZIP loading had already been hardened to reject missing requested annual JSON members. Imported Parquet directory loading, however, could still load only the available years and append `_PARTIAL_YEAR_COVERAGE` to an attribute. A multi-year research run could therefore complete and produce P/L despite an entire requested calendar year being absent. Merely tagging an attribute does not prevent downstream consumers from misinterpreting the results.

## Change

`src/norisk_quant/data.py::load_market` now preflights the complete **requested calendar-year set** for Parquet directory sources, before reading any Parquet partition:

- Missing accepted partition listed in a manifest: existing explicit error remains.
- No requested partitions at all: existing no-partitions error remains.
- Some requested partitions present but at least one year missing: fail with `Missing requested Parquet source years: [...]`.
- Single-year requests and December 31 inclusive end dates do not require adjacent unrequested years.
- ZIP behavior remains unchanged. The cache integrity status no longer emits a partial-year suffix for an accepted run because partial-year requests now fail.

A year being present does **not** prove every trading minute is present; minute gaps, source authenticity, bid/ask semantics, broker sessions, and incomplete final months remain separate audit responsibilities.

## Regression changes

`tests/test_cache_integrity_integration.py` now covers verified-cache missing first year, manifestless missing first year, manifestless missing intermediate 2025 between 2024 and 2026 (asserting no Parquet reads occur), and valid 2024-only scope. Existing missing-accepted-partition and year-end tests remain in the suite.

## Verification status

**Changes committed; full current-HEAD pytest, installed-package smoke tests, GitHub Actions CI, official frozen BOS sensitivity runner, and actual 13-field original Gold ZIP replay have NOT been executed or passed in this update.** The new tests are regression specifications, not passing-test evidence. The original source ZIP is not present in the execution environment.

Research and trading constraints remain unchanged: `$0.40/oz ALL-IN` fee, no live execution, no new strategy profitability claim, no raw quote upload, no public repository change, and PR #1 remains Draft.
