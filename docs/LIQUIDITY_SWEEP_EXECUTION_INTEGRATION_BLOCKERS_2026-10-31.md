# Liquidity-sweep execution integration: quote-side and provenance blockers (2026-10-31)

**Scope:** source inspection of `scripts/liquidity_sweep_signal.py` at PR #1 HEAD `6782b5bb40ad24a1a443cc4cda75efbd62535317`. This is an engineering review, **not** a historical backtest, independent OOS evaluation, or trading authorization.

## Verified signal-only contract

- `M1Bar` contains bid open/high/low/close and **ask open only**. `SweepSignal` contains side, decision/entry timestamps, entry, stop, target and reference prices.
- For long entries, the signal uses next-minute ask open; for short entries, next-minute bid open.
- The stop/target levels are derived from **bid-side** M5 extremes and a 1R price distance. There is no quote-side exit series in this signal module.
- The 240 completed M5-bar eligibility threshold is **20 observed hours**, not a proof of an entire 24-hour session or a broker's official trading calendar. Missing minutes can invalidate otherwise eligible days.
- No position lifecycle, maximum-hold exit, gap-through fill, same-entry-bar target deferral, or $0.40/oz accounting is implemented by this signal generator. Those must be delegated to and independently verified in the shared execution engine.

## Integration must fail closed

1. Preserve the complete original M1 **BID and ASK OHLC** source, with a SHA-pinned provenance chain. Never manufacture ASK high/low from ASK open or a fixed spread. A short stop is triggered by executable ASK prices, while a long stop is triggered by BID prices; target fills must follow the engine's documented quote-side rules.
2. Map signal timing into the shared engine without filling the just-closed M5 candle retroactively. Confirm that `signal_time == entry_time` in the current signal object represents the **M5 close / next M1 open boundary**, not an earlier decision.
3. Assert one position at a time, stop-first same-bar ambiguity, adverse gap-through behavior, no same-entry-bar target credit, 120 **observed contiguous** M1-minute holding cap, and canonical $0.40/oz all-in cost, using independent deterministic fixtures.
4. Compare the resulting trade ledger against a slow reference on all discrete and numeric execution fields; reconcile trade net, fees, weekly/monthly aggregates, and equity. No profitability claims from signal counts.
5. Keep all previously inspected years classified as research-exposed. Freeze source, code, execution settings, and acceptance criteria before any prospectively untouched evaluation.

**Release status:** BLOCKED for liquidity-sweep strategy backtest promotion until full quote-side execution integration and synthetic parity pass. Existing successful CI on signal-only tests does not satisfy this gate. Frozen BOS/H1 negative-control result is unchanged. Do not merge Draft PR #1 or upload original Gold ZIP.
