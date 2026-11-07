# Source M1 exit-bar consistency audit — 2026-10-29

## Scope and exact limitations

Added `norisk_quant.source_bar_exit_integrity.verify_source_bar_exit_prices` and wired it into the **actual** frozen annual BOS/H1 runner and independent archived-ledger parity script. This is a **BID-reference M1 OHLC consistency gate**, not broker execution, tick ordering, BID/ASK spread, margin, or clean out-of-sample certification. The previously existing `verify_source_open_exit_prices` remains responsible for adverse first-open stop exits.

The new gate independently checks the observed M1 bar for:
- `stop`: configured stop price is reported, the source range touches it, and the target is **not** also touched.
- `ambiguous_stop_first`: configured stop price is reported and the source M1 high/low touches **both** stop and target, consistent with conservative stop-first ambiguity.
- `target`: configured target price is reported, source range touches target **without** touching stop, and entry predates the exit minute (same-entry-minute target must be deferred).
- `open_target`: configured target price is reported, source opening BID already lies at or beyond the target in the favorable direction, and entry predates exit.
- `end_of_data`: at most one forced exit, on the last observed M1 timestamp, exactly at the final source BID close.

All audited exits require a unique, strictly increasing UTC minute-aligned M1 index; finite positive numeric non-boolean OHLC with valid bar geometry; unique trade fields; strict integer ±1 side; UTC-aware entry/exit times present in the source; and finite positive numeric exit/stop/target. No raw Gold data are committed. Report output now includes `source_bar_exits_verified_by_reason` alongside the pre-existing source-open stop count.

## Verification and release gates

**21/21 isolated synthetic tests passed locally** using the same new module and a minimal stub for the pre-existing quote dtype helper. These checks include both valid exits and deliberately identically corrupted exit labels/prices. The new test file is `tests/test_source_bar_exit_integrity.py`.

**Not yet verified on this HEAD:** full GitHub repository pytest/installed package, GitHub Actions, original private SHA-pinned Gold ZIP replay, archived 13-field parity on the new code, tick fills, or fresh untouched OOS. Prior CI successes apply only to their own commits. The original Gold ZIP SHA is `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` and must never be uploaded to the public repository. Frozen fee remains **exactly $0.40/oz all-in**. No strategy rules or historical P/L were changed; rejected BOS/H1 findings remain rejected. PR #1 stays Draft and unmerged.

## Caveat

A stop and target within one OHLC bar cannot establish the true order of intrabar touches. This check enforces the **simulator's stated conservative labeling**, not proof of what happened at a broker. Receipt-time causality and genuine synchronized BID/ASK ticks remain separate unfulfilled research requirements.
