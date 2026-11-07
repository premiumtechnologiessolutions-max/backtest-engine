# Exact historical 13-field replay: 1-ounce gross P/L and directional risk geometry

**2026-10-27. Code-only safety hardening; original Gold ZIP replay remains pending.**

## Previously unguarded failure mode

The historical comparator checked 13 matching fields, chronological order, positive
prices, the frozen $0.40/oz fee and net == gross - fee. However, two identically
corrupted ledgers could report a fabricated gross/net pair while still matching
all 13 fields. They could also match an impossible stop/target orientation.
This is a verifier contract gap, **not** evidence that the actual archived
gold trades contain these anomalies.

## Additional independent invariants

For **both** the current engine and the archived standalone ledger, after
strict 13-field equality:

1. In this **fixed 1-ounce** historical replay, verify
   `gross_pnl = side * (exit_price - entry_price)` with absolute tolerance
   `1e-7`, `rtol=0`. The existing `net = gross - 0.40` gate remains.
2. For a long (`side=+1`), require `stop < entry < target`.
   For a short (`side=-1`), require `target < entry < stop`.
   These are original order-risk levels; adverse gap-through stop fills
   may be beyond the stop but do not change the geometry check.
3. Synthetic regression cases include a paired fabricated gross/net pair,
   inverted long/short stops or targets, and a valid short control.

These checks **do not** change trade generation, execution, the fee model,
existing historical P/L, or strategy selection.

## Verification boundary

Six regression cases were committed with the change. Their inclusion does
not establish that the **full repository pytest or GitHub Actions passed on
this exact HEAD**. The authorized original `Gold data.zip` SHA-256 is
`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
The independent 13-field replay against that archive has **not been rerun
on this change**. The original ZIP and archived trade ledgers must remain
outside this public GitHub repository. PR #1 stays Draft/unmerged.

No OOS evidence, monthly-profit guarantee, broker tick-fill verification,
or live-trading approval is implied.
