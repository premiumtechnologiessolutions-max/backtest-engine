# Arithmetic replay: independent flat-position M1 floating-risk gate (2026-10-30)

## Finding and change

Reference/Fast agreement and a consistent persisted M1 equity identity
(`realized_pnl + floating_pnl = equity`) do not establish that a position
actually existed at the time of a floating mark. Both engines' exported
reports could contain identical fictitious floating profit or loss while
flat, with recalculated drawdown and summary values, and pass prior checks.

`scripts/run_arithmetic_dispatch_training.py` now reconstructs the number
of positions active at each **observed M1 minute close** from the ordered,
previously audited trade entry/exit timestamps. The canonical executor
books exits before emitting that minute's mark, so a position is active
at a mark iff `entry_at <= mark_at < closed_at`. The audit requires zero
floating P/L (tolerance `1e-7`) whenever that count is zero, rejects
occupancy outside the single-position contract, and requires all floating
marks to be zero when no trade was closed.

No unobserved M1 minutes are synthesized. The audit is independent of
both engines agreeing with each other, but it is **not** an independent
reconstruction of floating P/L during an open trade from broker prices.
The latter requires verified underlying Bid/Ask observations.

## Adversarial tests

Two identical-corruption integration fixtures alter (a) the minute of a
closed trade and (b) the minute before its entry. Each preserves the
reported realized P/L, equity arithmetic, drawdown arithmetic, annual
drawdown summary and Reference/Fast agreement, yet must be rejected.

A direct zero-trade test rejects fictitious floating P/L and accepts
the valid all-zero flat baseline.

## Boundaries

Synthetic tests only unless a separate successful test run is recorded.
No new original Gold ZIP backtest, 13-field historical replay, verified
forward OOS result, profitable strategy, or live-trading approval is
claimed. The canonical all-in cost remains exactly **$0.40 per ounce**.
Do not publish raw market data; keep PR #1 Draft.
