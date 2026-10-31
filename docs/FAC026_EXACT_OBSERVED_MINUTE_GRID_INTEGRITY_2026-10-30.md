# FAC026 exact observed UTC minute-grid integrity — 2026-10-30

## Independent audit finding

The previous FAC026 `candles()` completeness condition used only the number
of source rows and the elapsed time between the first and last row. It could
incorrectly accept a candle with **one duplicated observed minute replacing
one missing minute**, because the row count and endpoint separation remain
unchanged. A shifted fractional-minute grid could also be accepted by the
standalone scanner, although the SHA-gated `load_year()` already rejects
such malformed epochs for official original-source runs.

The gate now requires an exact UTC DatetimeIndex matching integer second
epochs, minute alignment, unique observed epochs within every M15/H1 bin,
and exact first/last UTC minute boundaries. Missing, duplicated, shifted or
misindexed minutes cannot be treated as a complete candle. The stricter
check is **only a data-integrity guard**, not a new strategy or new signal.

## Evidence and limitations

- Code: `scripts/research_fac026_original_source_structural.py`.
- Regression tests: `tests/test_research_fac026_original_source_structural.py`.
- Five new synthetic tests: duplicated replacement minute, subminute shift,
  timestamp/index disagreement, non-UTC index, missing last H1 minute.
- Original private Gold ZIP: **not available/replayed in this change**.
- New original-source backtests: **0**; monthly P/L, worst month, observed
  floating M1 drawdown: **N/A**; approved strategies: **0**.
- FAC026 frozen 32 correlated specs remain unchanged and historically exposed;
  earlier 18 unique structural timestamps / 13 empty months are NOT rerun
  or relabeled as prospective OOS.
- Execution contract remains next eligible open <= 1 minute, stop first,
  adverse gap-through and exactly $0.40/oz ALL-IN roundtrip; this gate
  does not simulate fills, shared capacity or realized-loss halts.
- PR #1 remains Draft/unmerged; no raw BID/ASK data is committed.

This is a targeted fix for false completeness, not proof of broker execution,
independent OOS, canonical source parity or profitability. CI status must be
checked on the exact final commit.
