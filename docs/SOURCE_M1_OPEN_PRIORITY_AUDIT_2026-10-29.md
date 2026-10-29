# Opening-price priority in independent M1 exit-bar audit — 2026-10-29

The limit simulator checks an existing position at the **first observed BID open** before evaluating the rest of that M1 candle. Its exit label is `open_stop` or `gap_stop` if the open is adverse beyond stop, and `open_target` if the open is favorable beyond target. A newly filled limit beyond stop uses `entry_open_beyond_stop`.

## Corrected audit gap

Previously `verify_source_bar_exit_prices` could accept an invented `stop`, `ambiguous_stop_first`, or `target` label when the bar's high/low touched the claimed price **even though its opening BID had already triggered a different exit path**. The audit now rejects those intrabar labels whenever the observed open crosses the stop or target, including equality within the existing 1e-7 price tolerance. This does not modify any strategy, executor, fixed fee, or archived research result.

Eight synthetic regression cases cover both directions: four adverse-opening stops falsely labelled as intrabar stops, two favorable-opening targets falsely labelled as intrabar targets, and two valid `open_target` cases where the subsequent M1 range also reaches the stop. The latter must remain valid because opening execution precedes the later unsequenced M1 high/low range.

## Verification limits

The code and regression cases are committed for the full repository pytest/CI gate; **no original private Gold ZIP replay, archived 13-field parity, or live tick/broker fill certification is claimed** by this change. No raw market data are committed. The all-in research fee remains **exactly USD 0.40/oz**; rejected BOS/H1 results remain rejected. PR #1 must stay Draft until the full current-head checks and authorized source replay succeed.
