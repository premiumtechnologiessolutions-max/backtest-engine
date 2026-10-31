# Source M1 opening-stop survival audit — 2026-10-29

## Scope

The existing `verify_source_open_exit_prices` checks that opening-stop fills agree with the source BID opening quote, stop direction, and gap/contiguity label. The full-OHLC `verify_source_bar_exit_prices` now also audits `open_stop`, `gap_stop`, and `entry_open_beyond_stop`. It uses the same chronological survival checks already applied to stop, target, open-target, and end-of-data exits.

For an old position, the audit rejects a recorded opening-stop exit if an observed M1 bar after entry but before the claimed exit touched either the stop or target. On the entry minute, a touched stop invalidates survival, while a same-entry-minute target remains deferred under the Limit engine's conservative unknown-sequence policy.

At the claimed exit, it verifies exact BID opening price (absolute tolerance `1e-7`), adverse-side stop direction, the required entry/exit timestamp relationship, and `gap_stop` versus `open_stop` using the immediately preceding observed M1 timestamp. For `entry_open_beyond_stop`, entry and exit must occur on the same source minute.

## Synthetic regressions

`tests/test_source_bar_open_stop_survival.py` covers long/short, contiguous and missing-minute stops, same-minute entry-open stops, earlier stop/target touches, entry-minute stop, mislabeled gap, invented fill, favorable-to-stop opening, and inconsistent entry chronology.

This is an independent audit of the recorded engine output; it does **not** prove tick ordering, broker fill quality, or real execution. Missing source minutes are not inferred. Source bar OHLC cannot prove the exact intrabar sequence. The source-open audit remains separate, with its open-only input contract intact.

## Research and release gate

No strategy parameters, execution fee, source archive, or OOS partition were changed. Frozen XAUUSD cost remains **USD 0.40/oz all-in**. Previous BOS/H1 historical negative findings remain unchanged. This change must not be described as a completed original-archive replay or 13-field parity rerun; the authorized original `Gold data.zip` is still needed in the execution environment for that acceptance gate. Keep PR #1 in Draft until repository-wide tests, source replay, and acceptance gates are verified. Never commit the private raw market archive.
