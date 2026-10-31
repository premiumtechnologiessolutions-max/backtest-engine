# FAC025: Strict pre-signal receipt/confirmation gate (2026-10-29)

**Status: research-only, synthetic regression; not a profitable strategy or broker-certified feed.**

## Failure mode and narrowly scoped remedy

A historical M1 candle may be timestamped at its market **open**, but its
complete OHLC can only be known after the candle closes and the feed delivers
it. A trade may have a market close timestamp while its *verified net result*
arrives later. Using either at a decision timestamp without a receipt audit
creates a silent **look-ahead / information-availability** risk even if the
market timestamps themselves are earlier than the signal.

Added `scripts/research_fac025_receipt_gate.py` with
`evaluate_gate_from_received_inputs`, an optional stricter adapter to the
existing observed-M1 FAC025 gate. Each M1 input must carry `received_at`,
the independently recorded time its complete OHLC was available; each closed
trade must carry `confirmed_at`, when its already verified net result was
available. Both must be strictly **before** the signal. An M1 receipt earlier
than `open_at + 1 minute` and a trade confirmation earlier than `closed_at`
are rejected. Strict UTC datetime and exact record schemas are enforced.
Malformed/future/same-instant observations fail closed; the existing M1
reconstruction, M15 completeness, session/DST, volatility, and daily-loss
filters remain unchanged. Receipt order need not equal market-time order
because delayed delivery is possible; every receipt still must precede
decision time.

**This does not authenticate caller-provided receipt timestamps.** Before any
real-source claim, record receipt timestamps from a trusted feed/audit log and
verify its clock, integrity, availability, and source BID/ASK side. A candle
being timestamped as closed does not itself prove its OHLC was published by
that instant. The original `evaluate_gate_from_observed_m1` remains a
research-only adapter for already audited inputs; do not call it a
receipt-certified path.

## Tests and unchanged scientific limits

`tests/test_research_fac025_receipt_gate.py` contains synthetic positive,
negative, boundary, delayed-receipt, stale-confirmation, malformed-schema,
nonfinite, and ordering regression cases. Check GitHub Actions on the exact
commit before claiming full-suite success. No raw Gold ZIP or private quotes
are committed. Frozen FAC025 candidate settings, monthly scorecards,
execution, registry counts, and the canonical $0.40/oz all-in fee are unchanged.

The historical BOS/H1 2,876-trade exposed-year study remains rejected
(0/48 profitable months, -$1,226.22560 USD/oz); these synthetic gate tests
are **not** new XAUUSD evidence, fresh OOS, live execution, or a guarantee
of monthly profitability. Keep PR #1 draft/unmerged pending all acceptance
gates and independent forward validation.
