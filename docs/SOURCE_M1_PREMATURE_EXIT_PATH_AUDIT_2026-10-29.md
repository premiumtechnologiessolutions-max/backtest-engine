# XAUUSD source-M1 premature-exit path audit — 2026-10-29

## Finding

An exit reason, timestamp and price can match the **reported closing M1 candle**
while still being impossible under the actual one-position Limit executor: an
earlier observed candle may already have touched the protective stop or target.
The previous source-bar verifier checked only the entry/exit timestamps and
the final bar, so it could accept an identically falsified execution/archive
ledger with a delayed but otherwise plausible exit.

## Change

`verify_source_bar_exit_prices` now checks the observed **path from entry
through the candle before exit**. For an entry-minute Limit fill, a stop
touch is immediately fatal; a target touch may be deferred because OHLC
does not reveal whether target preceded the entry. On every later observed
minute before the recorded exit, a stop or target touch means the position
should already have closed. For `end_of_data`, the final candle may not
have triggered either bound unless entry was on that final candle, in which
case only a target touch can be deferred.

The audit handles both long and short positions, retains the original
stop-first and adverse-open checks, and remains quote-bar consistency
checking rather than proof of intraminute sequencing, broker fills, or
independent profitability.

## Verification and limitations

- Added long/short earlier-stop and earlier-target regression cases,
  entry-minute stop, final-minute forced-exit, and deferred entry-minute TP
  cases to `tests/test_source_bar_exit_integrity.py`.
- Eight separately reconstructed predicate scenarios were checked locally;
  **these are not a full repository pytest run**.
- **Full pytest, current-head CI and original private Gold ZIP replay have
  not been verified for this change**. Do not label this patch release-ready
  until those gates pass.
- No source Gold ZIP or raw quotes were uploaded. No change to strategy
  settings, fixed all-in USD 0.40/oz fee, PR draft status, or billing.
- The repository is currently reported as **public** by GitHub metadata,
  despite the private-project requirement. Keep proprietary data outside it.

## Follow-up gates

1. Execute full pinned-environment pytest on the exact final branch HEAD.
2. Re-run the authorized source SHA-pinned 13-field historical replay and
   frozen annual runner on the same HEAD when the original ZIP is available.
3. Freeze a distinct liquidity hypothesis and truly uninspected forward
   samples before any profitability conclusion.
