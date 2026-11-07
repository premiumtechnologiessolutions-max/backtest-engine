# Frozen XAUUSD persisted trade exit-reason / price invariant audit — 2026-10-28

## Scope and finding

The annual frozen runner already checks a 15-field exported/executed ledger match
and independently reconstructs per-trade fee, gross P/L, and net P/L. However,
two **matching** ledgers could still report a named `target` exit at a price
below the configured target, or a `stop` exit at the target price, while all
financial calculations and exported values agreed.

The new `verify_persisted_trade_ledger` check fails closed for these contracts:

| Limit engine exit reason | Independently required exit-price relationship |
| --- | --- |
| `stop`, `ambiguous_stop_first` | Equal to configured stop (absolute tolerance 1e-7) |
| `target`, `open_target` | Equal to configured target (absolute tolerance 1e-7) |
| `open_stop`, `gap_stop`, `entry_open_beyond_stop` | No better than the stop for the position side (1e-7 numerical tolerance) |
| `end_of_data` | Allowed without a price-level assertion here; source M1 terminal-close proof is a separate requirement |
| Any other reason | Rejected |

The rule applies to **both** in-memory and persisted ledgers, after checking
row-by-row parity and independently reconciling fixed **$0.40/oz** fees,
gross/net P/L, protective stop/target geometry, and chronology.

## Evidence and limits

- New regression file: `tests/test_persisted_trade_exit_reason_invariants.py`.
- 11 deliberately matching but invalid synthetic cases and 11 valid synthetic
  cases are included in the committed test module.
- A locally reconstructed **exit-reason predicate only** passed **22/22**
  parametrized isolated checks. This is **not** execution of the repository's
  complete pytest suite or of the committed test module.
- **Not executed/verified on this commit:** whole-repository pytest, installed
  wheel tests, GitHub Actions, original authorized `Gold data.zip` replay,
  the 13-field independent historical reference comparison, or fresh OOS.
- This check does not establish that an actual M1 quote touched the level,
  the actual terminal close for `end_of_data`, a broker tick fill, or profitability.
- The original private Gold archive and detailed quote/trade ledgers were **not**
  committed. The repository is publicly visible; do not upload private raw data.
- The BOS/H1 strategy remains historically rejected. No trading strategy,
  $0.40/oz fee assumption, GitHub billing setting, or PR merge state was changed.

**Release gate:** keep Draft PR #1 unmerged until current-HEAD full tests,
authorized source replay, and CI succeed. Do not treat historical exposed years
as a new independent holdout.
