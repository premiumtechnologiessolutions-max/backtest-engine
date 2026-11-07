# Frozen annual per-fill fee and monthly evidence reconciliation — 2026-10-29

This hardens the previously committed `scripts/frozen_summary_integrity.py` check, without changing the frozen BOS/Fibonacci strategy or its results.

- Reject duplicated ledger columns, numeric-looking text, booleans and complex-valued evidence instead of coercing them into floats.
- Reconcile the sum of all twelve persisted monthly net values with the executed trade net, independent of the annual headline.
- Verify **each** filled trade was charged exactly **$0.40/oz ALL-IN roundtrip**; aggregate-only fee checks can miss compensating $0.20/$0.60 tampering.
- Preserve zero-trade annual ledgers with empty object-typed columns; do not fabricate trades or months.
- Add ten synthetic regression cases for these fail-closed conditions. Existing independent per-month UTC exit attribution and source-bar checks in the frozen runner remain mandatory.

This is a source-evidence integrity enhancement only. It is **not** a new historical strategy backtest, independent OOS, BID/ASK tick certification or shared-capacity FAC025 result. No original Gold data is included; monthly net and M1 floating drawdown from new original-source FAC025 replay remain **N/A**. Repository visibility is public; keep private quotes local and PR #1 Draft/unmerged.
