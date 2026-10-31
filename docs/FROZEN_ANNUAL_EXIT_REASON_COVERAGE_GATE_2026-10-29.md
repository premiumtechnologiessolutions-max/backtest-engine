# Frozen annual BOS/H1 — source exit-reason coverage gate (2026-10-29)

## Finding

The independent source-open and source-bar validators intentionally **skip unknown exit labels**. The official frozen annual runner previously recorded their counts without requiring the combined audit to cover every executed trade. A new executor exit path could therefore be omitted from source-price certification while monthly and weekly P/L totals still reconciled.

## Change

`scripts/run_bos_fib_frozen_sensitivity.py` now calls `verify_exit_audit_coverage` immediately after the two independent source checks and **before** report generation. It requires:

1. Every actual `exit_reason` to belong to the explicitly reviewed `AUDITED_REASONS` set.
2. Per-reason source-bar audit counts to equal the actual executed trade ledger, not merely the total number of trades.
3. The separate source-open audit count to equal the ledger count of `open_stop`, `gap_stop`, and `entry_open_beyond_stop`.
4. Exact reason-set coverage and nonnegative integer counts; boolean/float counts are rejected.

An unknown label, undercount, fabricated count, or inconsistent independent opening-stop audit now fails closed before writing annual reports. The source-bar checker remains intentionally permissive as a reusable diagnostic; the **official frozen runner** enforces complete certification.

## Synthetic-only verification

`tests/test_frozen_bos_sensitivity_contract.py` adds positive, empty-ledger, unknown-label, undercount, opening-count mismatch, invalid-count, reason-set drift, and full runner integration regressions. The integration test injects an unknown synthetic executor exit and asserts no annual report is written.

## Evidence boundary

This is a code and audit-coverage correctness change, **not a new XAUUSD strategy result**. No original Gold ZIP was uploaded or replayed. The immutable original archive fingerprint remains `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`; the fixed ALL-IN cost remains USD 0.40 per ounce. Previously inspected years are not clean OOS. No live fills, broker tick sequencing, or monthly profitability is certified. Keep PR #1 Draft and unmerged until original-source replay and independent forward validation.
