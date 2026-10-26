# Historical 13-field replay: nonfinite numeric and timestamp schema gate (2026-10-26)

## Failures reproduced before patch

1. NumPy `np.allclose([inf], [inf], rtol=0, atol=1e-7)` returns `True`. Two corrupt trade ledgers could therefore agree on infinite entry/exit/fee/P&L values and be incorrectly marked as matching.
2. Converting an archived fractional Unix timestamp such as `1704153720.5` to `int64` truncates the half-second, making it compare equal to a whole-second engine timestamp.
3. `pd.to_datetime(..., utc=True)` treats a timezone-naive engine timestamp as UTC rather than proving the original ledger recorded an explicit timezone.

## Changes

- `scripts/verify_bos_h1_parity.py::exact_ledger_check` now rejects nonfinite numeric fields on **both** ledgers before applying the existing strict `1e-7` numeric tolerance.
- Engine timestamps must be timezone-aware datetime values; archived Unix timestamps must be actual integers, not floats, booleans or strings. Whole-second alignment and exact Unix-second equality remain mandatory.
- Added nine regression cases in `tests/test_historical_parity_contract.py`: four paired-infinity numeric fields, three fractional archived timestamps, one naive engine timestamp, and one string archived timestamp.

## Verification and limits

Eight isolated local predicate checks passed under Python 3.13.5, pandas 2.2.3 and NumPy 2.3.5. **This is not full repository pytest**, which remains unexecuted for this commit. The original authorized Gold ZIP and independent archived trade ledger were unavailable here, so the actual 13-field replay was **not** rerun. GitHub Actions was not dispatched; quota restrictions remain documented.

This patch does not change strategy signals, execution rules, annual performance, the canonical USD 0.40/oz all-in round-trip fee, or raw data. PR #1 must remain Draft/unmerged until full pinned pytest, original-data replay, and CI success. No clean out-of-sample or profitability claims.
