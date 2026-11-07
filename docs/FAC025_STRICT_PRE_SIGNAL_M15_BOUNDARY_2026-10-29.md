# FAC025 — Strict pre-signal completed M15 boundary (2026-10-29)

## Causality defect and correction

The preregistered FAC025 research-only filter previously allowed an observed
M15 bar with `end_at == signal_at`. Its final high/low/close are not
provably available at the exact decision instant. This could introduce
same-instant lookahead even though future bars were rejected.

Now every M15 `end_at >= signal_at` is rejected **before** session,
volatility and realized-loss decisions. Earlier bars must remain strictly
ordered. A bar ending strictly before the signal may be used only inside
the unchanged 60-second staleness window. Real feeds also require separate
publish/receipt timestamp verification; this fix does not establish that.

Existing FAC025 synthetic fixtures now decide one second after the completed
bar. Eight new synthetic cases in
`tests/test_research_causal_session_strict_bar_order.py` cover same-instant
and future bars, microsecond/second/60-second valid boundaries, stale data,
loss-halt precedence, and future bars outside session.

## Research boundaries

FAC025's frozen 72 correlated parameter configurations represent **one**
hypothesis, not 72 independent hypotheses. No new original Gold M1
backtests, monthly P/L, verified M1 floating drawdown, independent OOS,
or shared-capacity portfolio were produced. The M15 count field is still
trusted; independently reconstruct it from actual observed M1 before
acceptance. The canonical fee remains exactly $0.40/oz ALL-IN roundtrip.
No private data, MT5 live trading, billing/privacy, or PR merge changes.
Keep PR #1 Draft/unmerged.
