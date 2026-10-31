# Source M1 limit-entry provenance gate — 2026-10-29

The full source-bar exit auditor now **requires** `entry_price` in the persisted Limit trade ledger. It checks positive finite non-boolean numeric entry price, strict BUY `stop < entry_price < target` or SELL `target < entry_price < stop`, and source-bar entry eligibility: BUY M1 low must reach the buy limit, SELL M1 high must reach the sell limit.

**Reason:** An exit can match the original BID candle perfectly while the alleged limit order was never eligible to enter. The old exit-only auditor could certify that fabricated entry. This gate uses the actual recorded `entry_at` candle and fails closed on missing entry-price provenance.

Scope: this validates the *possibility* of a limit fill from observed M1 BID OHLC, not intraminute ordering, bid/ask spread, queue priority, broker execution, or an OOS profit claim. The engine still defers same-entry-bar targets and applies stop-first ambiguity. It does not change strategy signals, fee ($0.40/oz), or the private market-data source.

Synthetic regressions cover impossible BUY/SELL entry touches, invalid geometry, missing/invalid entry prices, and valid entries. The official annual and 13-field historical replay runners already pass complete `result.trades` ledgers with `entry_price`. Original Gold ZIP replay on this commit remains required before historical certification.
