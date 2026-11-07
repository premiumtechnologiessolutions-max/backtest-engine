# FAC028 — preregistered causal session-volatility risk gate (2026-11-02)

Status: **FROZEN HYPOTHESIS ONLY — NOT EXECUTED, NOT APPROVED**. This document is a pre-results protocol, not a claim of new independent OOS evidence. Check registry fingerprints before scheduling. Historical 2012–2016 are exposed design periods.

## Distinct hypothesis
A **prior-session volatility shock gate** reduces the worst monthly downside of a single-capacity, session-limited breakout portfolio relative to the same entries without the gate. It is not an EMA/FAC005B parameter retune. Only *completed* UTC daily/session bars and prior completed H1 bars may determine state. No same-bar high/low, future minute, current-day full range, or post-trade loss may enter an entry decision.

## Frozen evaluation grid (24 configurations, one hypothesis)
- Session entry windows (UTC, fixed, no local DST conversion): [07:00,10:00), [12:00,15:00), [13:00,16:00).
- Prior 20 completed trading days' daily true-range median multiplier shock exclusion: 1.5 or 2.0.
- Prior completed H1 breakout lookback: 12 or 24 completed H1 bars.
- Stop distance: 1.0 or 1.5 times prior 20 completed daily true-range median, with position ounces normalized so initial planned risk is 1 USD/portfolio; reject zero/undefined volatility.
- Target: 1.5 times stop distance, fixed; no other adaptive fitting.
- Entry only at next eligible real M1 open within 1 minute of signal; one shared position across every configuration **when evaluating a chosen portfolio policy**. Independent parameter replays are screening diagnostics and cannot be summed as a portfolio.

Grid size: 3 × 2 × 2 × 2 = **24 parameter specifications, one causal hypothesis family**, not 24 independent hypotheses. No reranking or reoptimization after viewing later years.

## Execution and falsification
1. Verify original private ZIP SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` locally. Never publish BID/ASK M1 or ZIP.
2. Reject any duplicated formula identity in registry before executing; keep the canonical cost exactly **$0.40/oz all-in roundtrip**, stop-first, adverse gap-through, no fabricated minutes, actual source calendar and missing-data exclusions. Use an explicit timezone/DST audit.
3. Freeze immutable run fingerprint (dataset hash, source commit, formula, grid, years, execution engine version, fee, calendar, fill semantics) *before* opening P/L. Publish a hash and frozen manifest, never private rows.
4. Design-period screen reports **all 24 monthly net values** for each configuration in each year, trade counts, worst month, longest nonpositive streak, max M1 floating drawdown, fee totals, and zero-trade months. Recompute accounting from trade ledger; report N/A for unverified metrics.
5. Compare the shock-gated strategy against its matched ungated baseline with identical fills and shared portfolio capacity; report incremental worst-month risk, not only annual aggregate. Run canonical vs optimized parity on selected full trades and minute floating equity; discrepancies fail closed.
6. No claim of clean OOS from any historically viewed 2012–2016 results. Forward/prospective validation requires publish-once freeze, chronological embargo (at least 30 calendar days after training), multiplicity adjustment across all tried families, and untouched observations.
7. Halt **new entries only** when prior fully completed session volatility exceeds the frozen threshold. Existing positions remain subject to their original stop/target; do not halt based on current-month drawdown computed with future closes.

## Current measured outcome
New original-source M1 backtests: **0**. New monthly P/L: **N/A**. New floating M1 drawdown: **N/A**. Approved strategies: **0**. Do not add these 24 specifications to completed registry totals before verified execution and exact-head CI.
