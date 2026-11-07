# Quant Engine — independent cross-engine trade ledger parity

Added a **functional** comparison calculator in
`src/norisk_quant/cross_engine_parity.py`, intended for future execution
reports from our native simulator, LEAN and NautilusTrader.

Given a *verified inert* frozen quant blueprint and canonical 16-column
trade ledgers for **every** declared execution engine, it:

- Rejects incomplete comparators (cannot select only the best provider).
- Rejects duplicate trade IDs, naive timestamps, unsafe numeric types,
  missing accounting, mismatched strategies and invalid entry/stop/target
  geometry.
- Reconstructs each trade's P/L and the owner's fixed $0.40 per-ounce
  roundtrip accounting independently of its exported totals.
- Compares every trade ID and every price, timestamp, direction, quantity,
  fee, exit reason and gap field against the native reference.
- Detects changed execution prices even where TOTAL gross/net P/L matches.
- Gives deterministic bounded discrepancy counts, SHA256 report/ledger
  identities and never includes private trade prices in discrepancy messages.

**Important integration limit:** LEAN and Nautilus do NOT automatically
produce this canonical schema. Separate actual source-specific adapters must
be built and independently tested with their pinned vendor versions before
their trade exports can be compared. A common trade ID must be assigned from
the same frozen signal identity and not guessed from prices or dates.
The validator is useful independently today on synthetic canonical rows.

Even identical data from two engine exports is NOT independent broker
proof, OOS validation, tick path validation, true source provenance or
authorization to trade. Its output **always** stays UNVERIFIED.

No external runtime, subprocess, market source ZIP, broker account,
Gold backtest, or research campaign is started in this construction change.
