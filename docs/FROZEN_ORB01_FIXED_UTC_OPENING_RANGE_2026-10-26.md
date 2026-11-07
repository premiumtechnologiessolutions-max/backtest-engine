# ORB-01 — frozen fixed-UTC opening-range continuation (2026-10-26)

**PREREGISTERED BEFORE ANY PRIVATE HISTORICAL ORB-01 RUN.** Status: UNVALIDATED. This is a research candidate, not an executable trading recommendation. The user objective of stable positive months is not guaranteed. Unlike CEB-01's volatility squeeze and the earlier BOS/liquidity sweeps, this is a **time-anchored session opening-range continuation** with no squeeze, FVG, EMA, RSI, or optimized historical threshold.

## Fixed signal rule

- Build complete, UTC-anchored M15 candles from observed M1 BID OHLC; missing minute invalidates that M15 candle. No interpolation, no bar containing fewer than 15 M1 observations.
- Each UTC calendar date: require exactly the four complete M15 bars opening **06:00, 06:15, 06:30, 06:45 UTC**. Their maximum high and minimum low define a 60-minute opening range. UTC is fixed year-round and **is not London local time or a DST-aware London session**.
- Require opening range width **$0.75–$8.00** per ounce. Monitor contiguous complete M15 bars opening **07:00 through 10:45 UTC** (4-hour window). If any bar is missing, abort that day's signal search rather than crossing a quote gap.
- Only the **first** M15 candle whose close crosses beyond the opening-range high/low by at least **$0.20**, whose own open and preceding complete candle close were inside the range, may trigger. A long is a close >= range high + $0.20; short <= range low - $0.20. One signal maximum per UTC date; if its stop exceeds limits, do not wait for a later breakout that day.
- Signal confirmed only at the end of the M15 candle. Enter no earlier than next observed M1 open, max **1 minute** stale delay. Entry uses synthetic same-BID reference, not actual broker bid/ask/tick fills.
- Long stop distance = signal close minus opposite opening-range low + **$0.10**. Short stop distance = opposite high minus signal close + **$0.10**. Accept only **$0.75–$20.00**. Target **1.5R**. This distance is fixed when the signal closes and is applied from the next M1 entry price, so a quote gap may shift the absolute protective level.
- One open position globally, stop-first when M1 stop and target both touched, adverse gap-through at observed open, no same-minute replacement, and force a time exit at the first observed open at/after **360 minutes**. No trailing, averaging down, position scaling, or compounding.
- Exact synthetic cost **$0.40 USD/oz ALL-IN round-trip**, 1.0 ounce. Never add spread, slippage, or commission on top. Cost model is a simplifying assumption, not proof of live fill quality.

## Frozen stage-1 decision before observing results

Run **2012 and 2013 separately**, using the original private ZIP whose SHA-256 is `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Run both reference and fast execution and require trade ledger parity before releasing any annual score. Produce weekly, monthly realized-at-exit and observed minute-marked equity, full fees and floating drawdown. Require 12 calendar months with M1 observations each year. Do not upload source ZIP or private trade timestamps to GitHub.

**Advance unchanged to a later exploratory corroboration stage only if all three pass:** (a) >= **18/24 positive calendar months** across 2012 and 2013, (b) net positive in **each year**, (c) >= **75 executed trades in each year**. Otherwise **REJECT ORB-01** without tuning to rescue it. A pass is not independent OOS or proof of future positive months; previously explored historical data are not pristine holdout. Genuine independent forward/prospective evidence remains necessary. Keep PR Draft; no live trading.

## Reproducibility

Code: `src/norisk_quant/opening_range.py`, `scripts/run_frozen_opening_range.py`, `tests/test_opening_range.py`, `tests/test_frozen_opening_range_contract.py`. Run the private runner only after committing this specification and tests. Pin the exact Git SHA and full dependency versions in private audit outputs. Every run uses `SPEC_SHA` computed from the serialized frozen settings; never change settings after opening results without declaring a new distinct hypothesis ID.
