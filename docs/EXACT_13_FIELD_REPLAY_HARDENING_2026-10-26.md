# 13-field historical replay: exactness hardening (2026-10-26)

## Scope and invariant

The independent BOS/H1 replay comparator in `scripts/verify_bos_h1_parity.py`
compares 13 trade fields against a separately archived research ledger. This
change tightens *acceptance logic only*. It does not change market data, trading
rules, orders, execution, fee assumptions, or historical results.

## Defects closed

1. Timestamp comparison previously divided nanoseconds by 1e9 with integer
   truncation. A trade occurring at `00:02:00.500Z` could match an archived
   `00:02:00Z` timestamp. All current timestamps must now be exactly
   second-aligned and equal the archived integral Unix seconds.
2. The `side` and `gap_minutes` fields were compared with the same
   `1e-7` tolerance as prices and P/L. These are discrete fields and are
   now compared for exact numeric equality.
3. When both trade ledgers were empty, the comparator returned success without
   checking whether the 13 expected columns existed. Empty replay cases must
   now prove the same full schema before being accepted.

The `1e-7` absolute tolerance remains unchanged for continuous price/P&L
fields. Field order, trade count, reference mapping, and the canonical
`$0.40/oz` ALL-IN fee contract remain unchanged.

## Verification evidence and limitations

Four new repository regression cases were added to
`tests/test_historical_parity_contract.py`: subsecond timestamp drift,
fractional `side`, fractional `gap_minutes`, and empty-schema enforcement.
A separate local copy of the comparator passed five synthetic checks
(including a valid baseline and valid empty case); **this is not a full
repository pytest run** and does not validate the installed package.

The original `Gold data.zip` with expected SHA-256
`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`
and independent historical reference ledger were not available in this
execution environment. No 13-field actual-data replay has been rerun on this
commit. Previous 2012 matching evidence applies to the earlier audited
snapshot only. Do not claim current-head historical acceptance.

The private PR remains Draft pending full current-head pytest, pinned
environment validation, original-data replay and CI. No raw market data
was uploaded, no GitHub Actions quota/spending settings were changed,
and no new strategy optimization or OOS claim is made.
