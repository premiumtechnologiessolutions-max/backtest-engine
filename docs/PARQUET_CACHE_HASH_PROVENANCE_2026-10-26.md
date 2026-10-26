# Imported XAUUSD Parquet cache integrity — 2026-10-26

## Problem / risk

The earlier importer recorded the SHA-256 of the original ZIP and of each
annual JSON member, but did **not** bind the generated Parquet bytes to its
manifest. `load_market(directory, ...)` revalidated prices and timestamps, yet
an altered **valid-looking** cached Bid/Ask price could pass those gates.
That could change trade outcomes without an obvious source revision.

## New, opt-in-by-data-format behavior

For **new imports**, `import_gold_zip` now writes a format-version-2
manifest. Every accepted annual partition records:

- `parquet_sha256`: SHA-256 of the exact compressed Parquet file bytes.
- `loaded_m1_bidask_sha256`: versioned SHA-256 of the original M1 UTC
  timestamps and eight Bid/Ask OHLC fields, via `fingerprint_loaded_m1`.
- The existing original archive/member SHA-256, row count and quality fields.

On directory loading, `load_market` now checks the manifest structure,
partition approval, file existence, Parquet file digest, the **entire annual**
M1 quote/timestamp integrity, year, row count, and semantic Bid/Ask
fingerprint **before slicing** the requested dates. A mismatch raises
`ValueError`; no corrupted rows are silently repaired or skipped.

The result's `DataFrame.attrs["cache_integrity"]` records one of:

- `MATCHED_IMPORT_MANIFEST_SHA256` (all loaded partitions have file hashes);
- `UNVERIFIED_LEGACY_OR_NO_MANIFEST` (older manifest or no manifest);
- an additional `_PARTIAL_YEAR_COVERAGE` suffix if some calendar years
  in the requested range have no partition.

The CLI includes this status as
`summary.json -> source_fingerprints -> cache_integrity_status`.
A direct standalone Parquet read is marked `UNVERIFIED_DIRECT_PARQUET`.

Version-2 manifests are now **fail-closed**: for each accepted year,
both `parquet_sha256` and `loaded_m1_bidask_sha256` must exist as valid
lowercase 64-character hexadecimal digests. Removing either field or using
an unsupported/non-integer `format_version` rejects the manifest **before
Parquet reading**. This prevents silently interpreting a damaged v2 import
as a legacy cache. Rejected-year entries do not need data digests.

Legacy version-1 caches remain usable **but must not be described as
hash-verified**. We do not invent or backfill a digest and call it original.
If a manifest explicitly accepts a year but its partition is missing, or
a listed partition is rejected, loading fails. A missing year is **not**
interpreted as a flat market or filled with artificial candles.

## Security and research limits

- An editable manifest plus file hash checks **consistency**, not authenticity.
  An attacker who can rewrite both the Parquet and manifest could still
  falsify them. The original Gold ZIP must be authenticated separately using
  the canonical archive SHA-256 and protected storage.
- This does not establish genuine tick paths, executable fills, actual broker
  costs, margin, or an independent out-of-sample period.
- Research trading fee remains **FIXED ALL-IN USD 0.40/oz per completed trade**.
  No additional spread, commission or slippage is charged.
- Raw Gold data ZIP/annual JSON, real ticks and credentials remain outside
  GitHub. No live orders or trading advice are involved.

## Verification and deployment status

- **15/15 isolated local tests passed** for the exact new
  `cache_integrity.py` helper (digest match, byte tampering, invalid hashes,
  duplicate years, malformed/legacy/missing manifests). They use synthetic
  bytes, not actual Parquet.
- Added integration tests in
  `tests/test_cache_integrity_integration.py` with a synthetic ZIP and mocked
  Parquet IO to cover manifest generation, SHA and semantic mismatch,
  missing partitions, legacy labeling and partial-year coverage.
  **These newly added GitHub integration tests have not been run in this
  runtime**, and the complete repository pytest suite / GitHub Actions
  have not been rerun for this commit. No CI success is claimed.
- `pyarrow` and the canonical raw archive were unavailable in the local
  runtime. No real-data replay or 13-field trade parity is claimed here.
- Keep Draft PR #1 unmerged pending full tests and a real-data provenance
  replay. Actions quota is still reported exhausted until 2026-11-01;
  do not alter billing or publish the private repository.

## Next acceptance gate

Run the exact committed installed package and full `pytest` with `pyarrow`,
import one real original year from the canonical private archive, verify
that the imported partition has both digests, reload it, and compare its
M1 Bid/Ask fingerprint and 13-field trade replay to the independent ledger.
Then enable CI only after Actions capacity is available.


## Version downgrade regression gate (2026-10-26)

- Added unit tests for missing v2 digests, unsupported version values and
  rejected-year compatibility.
- Added integration regression tests that remove each v2 digest from a
  synthetic import and require rejection before any Parquet read.
- Genuine legacy v1 test now declares `format_version=1` rather than
  deleting digest fields from a v2 manifest.
- An isolated local reproduction of the exact new manifest-validation
  predicate passed 11/11 controlled cases. **The complete committed GitHub
  pytest suite and the new integration tests have not been executed in this
  runtime**; do not interpret these checks as CI acceptance.
- A manifest can be edited or removed by a privileged actor. This is a
  consistency check, not cryptographic authentication of the market feed.
