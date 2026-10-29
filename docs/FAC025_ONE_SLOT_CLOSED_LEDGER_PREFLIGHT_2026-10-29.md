# FAC025 one-slot closed-ledger non-overlap preflight (2026-10-29)

## Purpose

The existing FAC025 receipt bridge reconciles the canonical 15-field ledger,
confirmed UTC receipts, and exactly **$0.40/oz ALL-IN roundtrip**. That alone
does not prove a **shared one-position portfolio**: two individually valid
trades can overlap in time and consume more than one slot.

`scripts/research_fac025_one_slot_audit.py` adds an optional research-only
**closed-history** preflight. It first reuses the canonical accounting and
preknown-receipt validator; then it rejects any next trade whose entry is
**at or before** the preceding trade's close. Equality fails closed because
M1 OHLC cannot prove the intraminute exit/re-entry order. The conservative
choice can reject legitimate same-minute re-entry; it never promotes one.

## Synthetic tests

`tests/test_research_fac025_one_slot_audit.py` covers empty and nonoverlapping
histories, multiple overlapping offsets, same-instant ambiguity, fee
tampering, future confirmation, out-of-order closes, nonlist inputs and
invalid stop geometry. This code is NOT an entry/exit strategy or an
independent source replay.

## What this cannot certify

A passing closed ledger does **not** verify the actual shared-capacity
execution path, suppressed/expired competing signals, still-open positions,
tick-order fills, original ZIP authenticity, monthly P/L, floating M1
drawdown or prospective OOS. Those metrics must remain **N/A** until the
frozen executable portfolio and source-verified replay exist. This module
never reads raw quotes, modifies the registry, sends orders or claims 12/12.

FAC025 remains one correlated frozen hypothesis with 72 settings, **zero
new original-data backtests and zero approved strategies**. The private
Gold ZIP must not be uploaded to the public repository. PR #1 remains
Draft/unmerged.
