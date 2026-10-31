# FAC025 — Strict known-before-signal trade-close boundary (2026-10-28)

## Finding

The research-only FAC025 New York session / M15 volatility / realized-loss gate previously accepted a closed trade with `closed_at == signal_at`. Even though it rejected future trade timestamps, a same-instant close has no guaranteed event ordering relative to the signal decision. Feeding that realized result into a daily loss gate can leak information not provably available when the signal was formed.

## Change

`scripts/research_causal_session_risk.py` now requires every provided closed trade to satisfy `closed_at < signal_at`, while retaining the existing chronological-order checks and the same New York-local date classification. Invalid numeric P/L is still rejected independently, including when the timestamp is otherwise invalid. This is a conservative causality rule; the gate does not place orders.

New synthetic regression cases: `tests/test_research_causal_session_strict_trade_order.py` covers equal-time negative, positive and zero outcomes; a close one microsecond earlier; a close one microsecond later; nonfinite P/L at the decision timestamp; and a prior New York calendar day.

## Evidence limits

These are committed tests, **not** a claim of current-HEAD full `pytest` or GitHub Actions success. No authorized original Gold ZIP replay was executed. No strategy, portfolio priority, broker/tick validation, new OOS sample, fee model, repo visibility, billing or PR merge was changed. The fixed all-in transaction cost remains **$0.40 per ounce** in canonical execution. FAC025 remains a research-only filter without a frozen entry/exit policy, and its 72 correlated configurations are not 72 independent discoveries. PR #1 remains Draft.
