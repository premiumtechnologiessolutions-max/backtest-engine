# BID/ASK quote dtype fail-closed gate — 2026-10-26

This change rejects nonnumeric and boolean price-column dtypes at three
independent boundaries: normalized raw M1, direct/partition Parquet validation,
and the observed M1 fingerprint function. Previously, `to_numpy(dtype=float)`
could coerce string prices or booleans in a cached frame to floats; the frame
could then pass numerical OHLC checks and even produce the same semantic
fingerprint as properly typed numeric quotes. This was a schema-integrity
blind spot, not evidence of actual tampering or a proven trading discrepancy.

Raw CSV/JSON numeric-looking text is still accepted only through explicit
`pd.to_numeric` conversion in `normalize`. Cached Parquet and fingerprint
inputs must already be numeric and nonboolean. All eight BID/ASK price columns
are checked. No prices, trade rules, fee assumptions, or raw data were changed.

Synthetic regression tests: `tests/test_quote_dtype_contract.py`.
Validation status must be read from the **exact resulting commit's** CI run;
this document does not itself certify the entire repository, original Gold
ZIP 13-field replay, or actual broker fills. Keep PR #1 Draft and unmerged.
