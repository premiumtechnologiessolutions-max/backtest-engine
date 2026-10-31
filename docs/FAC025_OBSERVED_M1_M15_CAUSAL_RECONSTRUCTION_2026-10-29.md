# FAC025 — Reconstruct complete M15 only from observed M1 (2026-10-29)

**Research-only synthetic verification. No new original-source XAUUSD backtests, monthly P/L, M1 floating drawdown, independent OOS, or strategy approval.** The frozen 72 parameter settings remain one correlated hypothesis, not 72 independent hypotheses. Registry totals must not change.

## Narrow safety improvement

The new module scripts/research_fac025_observed_m15.py introduces a strict **single quote-side** M1-to-M15 constructor and evaluate_gate_from_observed_m1 adapter. Unlike directly trusting the externally supplied observed_m1_count=15 in evaluate_causal_gate, this adapter computes the count from chronological unique UTC minute-open observations, builds each observed M15 high/low/last close, and feeds the existing gate. A missing M1 yields an incomplete M15; a wholly missing quarter-hour remains a gap; missing recent M15 yields a stale signal. No synthetic bars, interpolated minutes or future OHLC are inserted. A source row with a minute close or quarter-hour close **at or after** the signal timestamp is rejected. All OHLC prices must be finite positive non-boolean and internally consistent. The constructor rejects non-UTC, misaligned, duplicate or out-of-order rows, and bounds its input length.

This is an optional safe adapter, **not** a change to the frozen FAC025 signal/entry grid or a completed portfolio backtest. The original gate remains available for preverified M15 input. A trusted market-feed receipt/publish timestamp and independent reconstruction of bid/ask source fields are still required before real-source claims. Input is already-observed minute-open OHLC on one quote side, **not** a trading fill model or an implicit conversion between BID and ASK.

## Validation and remaining gates

Synthetic regression tests exercise complete and missing M1, whole-quarter gaps, stale context, strict same-instant boundaries, malformed/boolean/nonfinite quotes, non-UTC timestamps, and preknown realized-loss halt. Verify full exact-head GitHub CI before reporting a passed test count. No private Gold data.zip or raw M1 data is uploaded.

To run real original-source research, first freeze an independent entry/exit specification and one-slot shared-capacity policy; use SHA256-pinned original Gold ZIP privately, exact $0.40/oz ALL-IN roundtrip, next eligible open <=1 minute, stop-first and adverse gap-through, source-verified monthly and floating M1 drawdown, canonical reference/fast parity, chronological embargo and prospective independent evaluation. No live MT5, no billing/privacy change and PR #1 stays Draft/unmerged.
