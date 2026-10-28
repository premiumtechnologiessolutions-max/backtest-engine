# Frozen UTC exit-date boundary gate — 2026-10-28

This change makes the existing independent trade-exit period reconciliation check enforce **inclusive frozen research start/end UTC calendar dates**. Previously, monthly and weekly totals could agree while an exit occurred just before the declared start or after the declared end **inside the same month/week**. Such an out-of-window trade must not be certified.

`audit_run` now passes the frozen `spec["start"]` and `spec["end"]` to `verify_exit_periods`. The verifier checks canonical dates, UTC-aware close timestamps, and that every trade exit is within the inclusive interval. Its old three-argument API remains available for standalone period-only checks. Synthetic tests cover before-start and after-end cases with unchanged period totals, valid bounds, and malformed or reversed bounds.

**Scope:** this is a report-evidence gate, not an execution-rule change. It does not certify that entry timestamps are causal, that quote data are authentic, that the broker would fill orders, or that any strategy is profitable. No market ZIP, raw quotes, or trade ledger was committed. Historical exposed research is **not independent OOS**. Preserve the fixed $0.40/oz ALL-IN fee and keep PR #1 Draft until independent replay/release gates are satisfied.

**Verification:** record the actual GitHub Actions result for the exact new commit; do not infer CI success from earlier heads.
