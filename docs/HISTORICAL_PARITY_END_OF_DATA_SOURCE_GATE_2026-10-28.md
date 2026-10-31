# Historical BOS/H1 replay: end-of-data market-source cross-check

Date: 2026-10-28 UTC. Scope: independent archived 13-field replay verifier.

## Defect addressed

Two identical historical ledgers can agree on all 13 execution fields and pass
internal P/L and exit-reason checks, while both claim an arbitrary
`end_of_data` fill. The one-position M1 limit engine actually forces an open
position closed at the **last observed M1 candle's BID close**, with the
**timestamp of that candle**. Ledger-to-ledger agreement alone cannot prove
either fact.

The verifier now independently cross-checks any `end_of_data` row against
the already loaded, SHA256-pinned original M1 source. It rejects incorrect
last-candle timestamp, incorrect final BID close, and multiple forced final
exits for the single-position executor. The check occurs after the archived
13-field comparison and before marking the scenario PASSED.

Synthetic regression cases deliberately corrupt BOTH ledgers identically to
show that ordinary 13-field equality is insufficient. They do not access or
upload private Gold data. This is source-consistency verification only: M1
cannot establish real broker tick ordering, slippage or execution quality.

## Acceptance status

The original Gold ZIP replay **must be rerun on this exact new commit** before
claiming updated source parity. Historical exposed BOS/H1 losses remain
unchanged; no strategy is approved. Keep PR #1 Draft and do not merge.
