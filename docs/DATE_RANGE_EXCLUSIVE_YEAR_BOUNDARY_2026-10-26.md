# Inclusive end dates and annual partition selection — 2026-10-26

## Observed defect

`load_market(path, start, end)` promises an inclusive UTC end **date**.
Internally it correctly constructs an exclusive bound `finish = end + 1 day`.
However, both the ZIP and imported-Parquet directory branches previously
selected annual members with `finish.year` inclusive.

For `start=2024-01-01, end=2024-12-31`, the exclusive bound is
`2025-01-01T00:00Z`. The old annual selection therefore included **2025**.
Consequences:

- A manifest that explicitly accepted 2025 but had no 2025 Parquet file
  could fail a perfectly valid **2024-only** research run.
- A manifestless cache with no 2025 file could falsely label the 2024
  research slice `_PARTIAL_YEAR_COVERAGE`.
- An unrelated duplicate/corrupt 2025 member in a source ZIP could
  invalidate a 2024-only request.

This is a **date-scoping and provenance-reporting bug**, not evidence of a
profitable strategy or a change in historical quotes.

## Correction

Define `last_included_year = (finish - pd.Timedelta(nanoseconds=1)).year`
and use that year for ZIP selection and both annual partition loops.
This preserves inclusive `end` dates while respecting the exclusive
timestamp bound. Explicit cross-year requests continue to load both years.
Reversed date ranges are rejected before opening source data.

## Regression tests

`tests/test_year_boundary_cache_scope.py` contains synthetic tests for:

1. A Dec 31 end with an accepted **missing next-year** cache partition.
2. No false partial-year status for a manifestless Dec 31 cache request.
3. Ignoring duplicate ZIP members belonging only to the unrequested next year.
4. Rejecting a reversed date range before source access.
5. Loading **both** years when the user explicitly requests Jan 1.

No real XAUUSD data, private source archive, credentials or ledgers are
committed. Tests monkeypatch Parquet reading and do not establish pyarrow,
broker tick execution or 13-field historical trade parity.

## Verification status

- **6/6 isolated local calendar-boundary checks passed** on the extracted
  date-selection expression (including leap day and reversed dates).
- The five newly committed integration/regression tests **have not been
  executed against the full GitHub package** in this environment.
- Full repository pytest, installed-wheel acceptance and GitHub Actions
  for this commit remain **unverified**. The recorded Actions quota issue
  is not bypassed and no billing settings were changed.
- Preserve the canonical `$0.40/oz` ALL-IN research fee, original data
  SHA-256 verification requirement and Draft PR #1 status.
