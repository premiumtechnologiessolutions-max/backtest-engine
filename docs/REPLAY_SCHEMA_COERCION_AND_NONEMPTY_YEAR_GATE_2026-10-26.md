# Independent 13-field replay: type-coercion and nonempty-year gates (2026-10-26)

## Scope

This change hardens the *acceptance checker*, not strategy logic, market data, fill rules, or research profitability. The checker compares current-engine trade rows to the separately archived historical trade ledger. It is not a substitute for executing the real original archive.

## Failure modes closed

1. The previous numeric comparison converted all cells to float before comparing. That converts boolean `True` to `1.0`, and numeric-looking text such as `"100.0"` to a numeric price. A matching value could therefore conceal a malformed source or output schema. Numeric replay fields now require genuine numeric Pandas dtypes and explicitly reject boolean dtypes before finite-value and absolute-tolerance checks.
2. The previous `exit_reason` comparison converted both sides to strings. Numeric code `1` and text `"1"` could appear equal. Exit reasons now require nonempty string values on both sides and compare the original values without string coercion.
3. Calling `verify(..., years=[])` previously returned `status=PASSED` with zero scenarios. Duplicate years could double-count scenarios. `validate_replay_years` now rejects empty, duplicate, noninteger, boolean and out-of-source-range years before reading the ZIP.

## Tests and evidence

- 29 new parametrized regression cases were committed to `tests/test_historical_parity_contract.py`: 12 numeric coercion cases, 6 exit-reason schema cases, 1 positive case, 9 invalid-year cases, 1 positive-year case.
- Six small isolated local Pandas/NumPy checks reproduced the old coercion behavior and confirmed the new dtype predicate; **these are not execution of the repository's tests**.
- The modified files were fetched back from GitHub and the presence of all changes and test functions verified.
- The **complete repository pytest suite has NOT been run on this HEAD**. The original authorized Gold data.zip and the archived independent trade ledger are unavailable in this runtime, so the actual 13-field market replay has NOT been rerun.
- The most recent visible GitHub Actions runs are failed jobs from 2026-10-25; there is no successful CI run for this commit. CI remains manual-only due previously documented quota exhaustion.

## Remaining mandatory acceptance gates

1. Run `python -m pip install -c constraints-ci.txt -e ".[dev]"` in the pinned Python 3.12 environment.
2. Run `python -m pytest -q` on this exact commit; investigate any failure rather than asserting success from isolated checks.
3. With the authorized original ZIP and separately archived ledgers *outside GitHub*, run `scripts/verify_bos_h1_parity.py` and check all 13 execution fields, including the previously verified 2012 cases. Never upload raw quotes to GitHub.
4. Run the official frozen annual sensitivity runner end-to-end and reconcile reports; its current-head successful execution remains unverified.
5. Confirm CI green when quota permits. Keep PR #1 Draft/unmerged until all required gates pass.

**No market-data upload, cost change, strategy retuning, OOS claim, monthly-profit guarantee, or live-trading endorsement.** Fixed research cost remains USD 0.40 per ounce ALL-IN.
