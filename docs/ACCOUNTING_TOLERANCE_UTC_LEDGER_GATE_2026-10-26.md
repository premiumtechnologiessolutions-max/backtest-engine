# Accounting tolerance and UTC ledger parity gate — 2026-10-26

## Reproduced defects

1. `validate_execution(result, settings, atol=float("inf"))` passed the former `atol <= 0` guard. NumPy `allclose([0], [999], rtol=0, atol=inf)` can return `True`, allowing arbitrarily wrong cost, gross/net P/L and realized-equity reconciliations to be labelled PASSED. Large finite tolerances have the same weakness.
2. A valid `Signal` confirmed with an explicit non-UTC offset (e.g. `2024-01-02T02:01+02:00`) was written to the reference trade ledger with its original timezone, while the fast ledger normalized the same instant to UTC. The strict timestamp dtype/serialization contract diverged despite equal instants.
3. Both direct M1 executors previously accepted timezone-aware **non-UTC** candle indexes. This conflicts with the documented UTC M1 input contract and could create inconsistent trade/equity timezone representation.

## Fail-closed changes

- The accounting validator now accepts only a finite positive absolute tolerance in `(0, 1e-6]`; the default `1e-7` is unchanged. No changes to the canonical `$0.40/oz` ALL-IN round-trip fee.
- The reference executor canonicalizes accepted explicit-offset signal timestamps to UTC before recording trades, matching the fast executor. UTC signal inputs and their historical behavior are unchanged.
- Both Market execution engines now require UTC M1 indexes, as `load_market()` already supplies.

## Regression coverage and evidence level

New regression tests in `tests/test_accounting_integrity.py` exercise `inf`, `-inf`, `NaN`, zero, negative and large finite tolerances, deliberately corrupted fee/P/L, and an allowed bounded tolerance. Tests in `tests/test_subsecond_causality_and_quote_guards.py` check explicit-offset signal parity and non-UTC M1 rejection.

An isolated local Python reproduction verified the original infinite-tolerance bypass, offset timestamp dtype mismatch, and the revised predicates. **This is not a successful run of repository pytest.** The current private repository and original raw Gold ZIP are not mounted in that local Python environment, and `pyarrow` is absent there. Full source/wheel/sdist pytest, independent 13-field replay, and CI on the current head remain unverified.

The 2012–2016 QS01 design failure and exposed historical BOS/Fib results are not rerun or retuned. No private price data is committed. Keep Draft PR #1 unmerged until all acceptance gates pass.
