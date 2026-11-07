# XAUUSD liquidity-sweep research: preregistration protocol (2026-10-30)

**Status: design only; NOT executed; NOT evidence of profitability.** This document freezes a *new hypothesis* before any new evaluation. Historical years already explored anywhere in this project are **research-exposed**, even when a particular strategy has not been run on them. Do not label 2017–2026 clean OOS merely because this candidate is new.

## Hypothesis and exact causal construction

A prior-session extreme is swept by a completed M5 candle, followed by a completed M5 close back inside the prior range. Rejection may produce a short-lived mean-reversion move. This is a testable hypothesis, not an asserted edge.

1. Build UTC M5 bars only from **five consecutive observed M1 bars**; reject incomplete or non-contiguous windows. Use bid OHLC for long/short signal structure, and the actual loaded bid/ask columns for executable prices. Do not fill missing bars.
2. Reference levels at decision time are the **previous completed UTC calendar day's** highest bid high and lowest bid low, computed from fully observed M5 bars. Exclude days with fewer than 240 complete M5 bars; do not substitute partial days or the current day.
3. A **short** setup requires a completed M5 high strictly above the previous day's high by at least $0.20 and that same candle's bid close strictly below the previous day's high. A **long** setup requires a completed M5 low strictly below the previous day's low by at least $0.20 and that candle's bid close strictly above the previous day's low. Reject candles satisfying both directions.
4. Signal is known only at that candle's **close**. Enter at the **next contiguous M1 open**, ask for long and bid for short, with no retroactive same-bar fill. Reject if the next M1 bar is absent. Use the quote-side prices and fee conventions already enforced by the actual engine.
5. Stop for short: swept M5 high plus $0.10; for long: swept M5 low minus $0.10. Profit target is 1.0 times the **actual executable entry-to-stop risk**. Reject non-positive risk and risk > $20/oz. Maximum holding time 120 observed contiguous M1 minutes; a gap exits only under the engine's explicit gap rule, never with invented continuous bars. One position at a time; no pyramiding. Stop-first when both barriers could be touched in one M1 bar. No same-entry-bar target credit.
6. Apply the canonical **$0.40/oz all-in roundtrip cost**, one-ounce reporting, and original-source BID/ASK provenance. Do not silently double-charge the spread or remove costs. Do not optimize the above parameters on review data.

## Data governance and testing stages

- Stage A: write deterministic synthetic fixtures with positive and negative cases, including midnight boundaries, incomplete days, dual sweeps, missing next minute, spread, stop-first, time exit, and missing-bar handling. Validate entry timing against an independent slow reference.
- Stage B: execute only on **explicitly declared research/training data**, retaining the original ZIP outside GitHub. Log every experiment, parameter set, failure, and trade ledger; reconcile monthly/weekly net, fees, source prices, and file fingerprints. Compare against a no-trade baseline and an execution-matched randomized-direction negative control.
- Stage C: freeze implementation SHA, exact parameters, training cutoff, holdout selection, source SHA, pass/fail rules, and full attempted-family count **before opening a truly unseen future sample**. If all available historical years have already been inspected, the only credible untouched holdout is subsequently arriving data collected prospectively, not relabeled old years.
- Stage D: one authorized forward evaluation only, without repeated tuning against that same sample. Report every month including zero-trade months, net USD/oz, trade count, exposure, max drawdown, adverse costs/slippage sensitivity, and confidence intervals. Never assert guaranteed monthly profits.

## Acceptance and rejection

Engineering acceptance requires full repository pytest and CI on the exact commit, 13-field execution replay where applicable, and a source-backed positive-trade ledger with independently reconciled exits. Research promotion requires preregistered forward results after costs, enough observations to support uncertainty estimates, and a robustness check against plausible execution slippage. Any failing audit, missing month, look-ahead leak, unexplained discrepancy, or reused holdout is a **fail**, not a partial success.

**Current state:** 0 liquidity-sweep backtests under this protocol, 0 independently validated profitable months, 0 live approvals. This protocol does not supersede or alter the frozen BOS/H1 negative result.
