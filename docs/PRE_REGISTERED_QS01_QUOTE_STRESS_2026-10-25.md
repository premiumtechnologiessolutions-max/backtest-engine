# Preregistered hypothesis QS01 — quote-stress exhaustion (2026-10-25)

**STATUS: RULES FROZEN, NOT TESTED.** This is a distinct Bid/Ask microstructure proxy, not a BOS/Fib/H1 threshold adjustment, a trading recommendation or a claim about real tick sequencing.

## Frozen research contract

- Instrument: original private XAUUSD M1 BID/ASK OHLC. Timestamp is the **minute OPEN** in UTC. All signals exist only at the **minute CLOSE** (\`ts + 60 seconds\`). The data source ZIP SHA-256 is \`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121\`.
- For each observed M1 candle \`t\`, require **241 consecutive observed minutes** (no gaps or duplicates) ending at \`t\`; this ensures both 240-prior-minute spread baseline and 20-prior-minute ATR exist.
- Close-spread proxy: \`s_t = ask_close_t - bid_close_t\`; if negative, nonfinite or the preceding 240-minute median is <= 0, reject the signal. The baseline is the **median of s[t-240:t-1]** (exclude current).
- ATR: Wilder ATR(20) of BID true ranges on **completed M1 candles strictly before t**, including each candle's previous close. Require finite positive ATR and contiguous observations. Never use t's range in the risk estimate.
- Shock: \`s_t >= 2.5 × median_spread_prior_240\` and \`s_t <= $3.00\` (upper bound is a predeclared data-quality/liquidity guard, not an execution spread charge).
- Directional displacement: \`abs(bid_close_t - bid_close_(t-1)) >= 1.5 × ATR20_(t-1)\`. Trade the **opposite** side of that observed close-to-close displacement (sell after upward shock; buy after downward shock). If no strict direction, skip.
- Execute at **next observed M1 open** only if exactly 60 seconds after t. No retroactive entry after a market gap. One open position maximum, 1 oz fixed, no re-entry on same M1.
- Fixed stop distance \`1.5 × ATR20_(t-1)\`; target distance \`1.5 × ATR20_(t-1)\` (1R). Conservative M1 stop-first ambiguity and adverse gap-through at first observed open. Do **not** force-close solely because of a missing interval. Planned time exit after 30 elapsed UTC minutes, at the first subsequently observed open if still open, recording any gap exposure.
- Cost: **exactly $0.40 ALL-IN per oz per completed roundtrip**, once; no variable spread, slippage or commission on top. BID/ASK spread is a **predictor only**, not an extra trading cost.
- Research only: no leverage assumptions, broker fills, market orders on live accounts, or fabricated tick paths.

## Frozen evaluation order

1. Implement as a central-engine strategy, with tests proving no future spread/ATR/H1 observations, no gap lookahead, correct stop-first and fee-once behavior. Verify importer integrity and quote units.
2. **Design 2012–2016 only**, no parameter search: single fixed rule set above. Predeclared screening gate: at least 200 trades, net > 0, PF > 1.10, and >= 31/60 positive realized-P/L months. Failing any gate => reject without touching later periods for selection.
3. Only if design passes: evaluate **2017–2019** as chronological validation, with the same frozen rule set and without retuning.
4. **2020–2026 has been exposed repeatedly**; any later run is historical descriptive evaluation, **not independent OOS**. September 2026 is partial (through 2026-09-20).
5. Record full trade, weekly and monthly ledgers; realized and observed floating drawdown; count of ambiguous M1 bars and gap-through events; exposure, PF, worst month, and source/commit fingerprints. No cherry-picking of favorable months or retrospective per-month strategy switching.

**Important:** A wide quoted spread may signal low liquidity and *higher*, not lower, risk. A positive design result would still not prove broker fill feasibility or a monthly-profit guarantee. This is an untested hypothesis, not an accepted strategy.

## Implementation checkpoint (2026-10-25; no historical profitability run)

- Frozen signal code: `src/norisk_quant/qs01.py`, requiring exactly 241 contiguous observed M1 candles, 240 *prior* close-spreads, and *prior* Wilder ATR20. Bid/Ask close-spread is only a predictor.
- The opt-in `Settings(max_entry_delay_minutes=0, max_hold_minutes=30)` now supports the previously frozen **30 elapsed UTC minute** time exit at the first subsequent observed open. The reference and fast engines check gap-through stop and target at the open **before** a time exit. Defaults for other strategies are unchanged (`max_hold_minutes=None`).
- CLI: `norisk backtest --strategy qs01 --timeframe M1 --ounces 1 --all-in-cost-per-ounce 0.40 --execution reference|fast ...`. Any other timeframe/ounces are rejected.
- `tests/test_qs01.py` and `tests/test_qs01_runner_contract.py` cover causal signals, missing M1, stop-first gap precedence, time exits, fixed cost and reference/fast parity **when run**. This checkpoint has only locally executed the four extracted signal-generation tests (4/4 passed); full repository tests, remote CI, and reference/fast time-exit parity tests have **not** been executed successfully yet.
- Design-only authorized source runner: `scripts/run_qs01_frozen_design.py`. Requires the exact private original archive SHA-256, uses only **2012–2016**, writes full trade/equity/week/month ledgers and a strict 200 trades / positive net / PF>1.10 / >=31 positive months gate. No automatic access to validation years.
- **No QS01 real-data performance results exist at this checkpoint.** Never interpret code implementation or a synthetic unit test as design qualification, clean out-of-sample success, broker execution, or 81/81 monthly profitability.
