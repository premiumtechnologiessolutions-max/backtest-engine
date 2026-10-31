# Exact 13-field replay: discrete field type gate (2026-10-26)

## Issue reproduced

The prior comparator used `np.array_equal()` for `side` and `gap_minutes`.
NumPy considers `True` equal to integer `1`, and `1.0` equal to integer `1` (likewise `0.0` and `0`). Consequently, a malformed reference or engine ledger could pass the so-called exact 13-field replay despite violating the discrete-field schema. This is a comparator contract issue, **not evidence that historical trades were wrong**.

## Fail-closed correction

`scripts/verify_bos_h1_parity.py::exact_ledger_check` now checks both the actual and independently archived columns before comparing:
- `side` must contain true integer values, never boolean/floating values, and each value must be `+1` or `-1`.
- `gap_minutes` must contain true integer values, never boolean/floating values, and must be nonnegative.
- Values must match exactly and in order; price/P&L tolerance remains `1e-7`, timestamps remain exact whole Unix seconds, and all 13 columns remain mandatory, even for zero trades.

`tests/test_historical_parity_contract.py` now includes 12 negative cases across actual/reference ledgers and one explicit integer-positive case.

## Verification boundary

An isolated local pandas/NumPy reproduction confirmed the old `np.array_equal` bypass and the proposed integer checks on 12 synthetic predicates. This is **not** a successful run of current-repository pytest or the real-data 13-field replay. The original authorized Gold ZIP and independent historical ledger are not available in the current execution container. No historical strategy was rerun, no raw market data was uploaded, and no new OOS claims were made.

Keep Draft PR #1 unmerged until full pinned pytest, original-archive replay, and CI success. Canonical all-in research cost remains **USD 0.40 per ounce per round trip**.
