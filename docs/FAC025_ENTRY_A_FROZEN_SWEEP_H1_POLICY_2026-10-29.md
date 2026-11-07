# FAC025-ENTRY-A — frozen M15 sweep/reclaim + prior H1 trend intent (2026-10-29)

**Pre-outcome registration.** One fixed entry/exit *intent* policy layered on the already frozen FAC025 72 correlated filters. **Not 72 independent hypotheses.** No original Gold ZIP was opened for this policy before registration; 0 new original-data backtests, 0 observed monthly P/L, M1 floating DD N/A, 0 approved strategies. All 2012–2016 data are historically exposed and cannot be relabeled clean OOS.

## Exact frozen policy and hash

`FAC025-ENTRY-A`, version 1; four **previous** fully observed contiguous M15 bars; candidate last completed M15 must sweep the previous four lows and close back above their minimum for BUY, or sweep the highs and close below their maximum for SELL. Require two prior complete H1 bars (each four observed contiguous M15 bars) with last H1 close > earlier H1 close for BUY, or < for SELL. Both H1 bars must finish **no later than the start** of the candidate M15; never use the unfinished/current H1. Ambiguous dual signals are blocked. The prior FAC025 New York DST session, observed M15 volatility, receipt-time and verified realized-loss gates must all pass **before** proposing an intent.

Normalized prospective stop distance: max(candidate M15 BID close-to-swept-wick distance, BID close × 0.0004). Block if this exceeds BID close × 0.0015. Fixed target distance = 1.50 × stop distance. The prospective stop/target are *distances only*, not executable prices: actual entry must be a separately verified **next eligible observed open within 60 seconds** after the decision; no fill price or position size is guessed. Shared capacity is one position, but this intent generator does **not** enforce it. Fixed exactly $0.40/oz ALL-IN roundtrip is a future executor requirement; no fee/P/L is fabricated here. Gap-through is adverse, stop-first, no interpolated M1, no same-instant H1 confirmation.

Canonical JSON policy (sorted keys, compact ASCII separators) SHA256:
`f4378cdee27d247864fad77895137c709b7fb674b27c3f2aef77c16419015eee`.

Implementation: `scripts/research_fac025_frozen_entry_policy.py`; synthetic tests: `tests/test_research_fac025_frozen_entry_policy.py`. This code uses the frozen filter fingerprint and canonical paired BID/ASK receipt gate, then reconstructs only previously received complete M15 from observed BID M1. Source receipts remain caller-supplied and **not independently authenticated**. A generated `RESEARCH_INTENT_ONLY` is not a trade, not a backtest, not a profitable strategy, and not proof of capacity or fills.

## Required next gates

1. Implement independent source-pinned replay of this *unchanged* policy on private SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`; do not upload raw BID/ASK to public GitHub.
2. Implement actual one-slot shared-capacity signal priority and canonical execution (next observed eligible open <=60s, stop-first, adverse gaps, $0.40/oz ALL-IN). Verify reference vs fast ledger, monthly net and observed M1 floating equity, fee reconciliation and worst month. Count real fills and reject low sample sizes.
3. Keep a frozen untouched prospective source manifest, embargo, multiple-testing controls and no historical OOS claims. Keep PR #1 Draft/unmerged; no live MT5 or billing/privacy changes.
