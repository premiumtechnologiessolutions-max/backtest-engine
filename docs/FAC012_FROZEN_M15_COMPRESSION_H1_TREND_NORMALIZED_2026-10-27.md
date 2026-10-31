# NRF-FAC-012 — FROZEN BEFORE PRIVATE RESULTS (2026-10-27)

**Status: PREREGISTERED; ZERO FAC012 REAL-DATA RUNS AS OF THIS COMMIT.** Never backfill the precommit status. Historical 2012/2013 were previously inspected by other campaigns; this is design-only, NOT clean OOS.

## Independent signal family
Completed M15 *compression-to-range-break* rather than Donchian trend continuation, wick rejection, MAD recross, EMA cross or directional run. For each fully observed M15 bar j, the **preceding** M15 bar j-1 must have range <= squeeze_multiplier × the median range of the 20 bars j-21..j-2. The current fully closed M15 **close** must break strictly above the previous N completed M15 highs (buy), or strictly below the previous N completed lows (sell). Require a continuous M15 segment spanning j-21..j (no fabricated gap candles). Signal timestamp is close_at(j), never before.

Risk reference is the same **prior-20** M15 range median, strictly positive, computed without current or preceding squeeze candle. SL distance = risk_reference × stop_multiplier; TP distance = risk_reference × target_multiplier, both frozen on signal confirmation, never adapted to future prices. This is risk normalized by pre-known local volatility, not a fixed-dollar grid.

Last completed H1 candle as-of signal (age 0..3600s) supplies EMA8 versus EMA24 direction (H1 EMA reset after gaps; >=26 consecutive completed H1 bars) and H1 current range / **prior 24 consecutive completed H1 ranges** median. If the ratio exceeds the max H1 volatility gate, suppress the signal; this is a causal *pre-trade halt*, not a P/L-based halt. H1 trend mode ALIGNED trades in breakout direction; CONTRA reverses breakout side. Local DST session masks apply at signal close: ALL, Europe/London 08:00–12:00, America/New_York 09:30–13:30.

## Exact frozen grid (24,000 parameter IDs per annual replay)
- Breakout lookbacks: **4, 6, 8, 12, 16** (5).
- Squeeze multipliers: **0.55, 0.75, 0.95, 1.15** (4).
- H1 trend modes: **ALIGNED, CONTRA** (2).
- H1 volatility halt maximum ratios: **1.20, 1.80** (2).
- Sessions: **ALL, LONDON_LOCAL_08_12, NY_LOCAL_0930_1330** (3).
- Normalized SL multipliers: **0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50, 2.75** (10).
- Normalized TP multipliers: **0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50, 2.75** (10).

5 × 4 × 2 × 2 × 3 × 10 × 10 = **24,000 correlated parameter specifications**, not 24,000 independent hypotheses. Plan: 2012 and 2013 independently reset annual M1 replays = **48,000 planned** annual executions and 576,000 planned monthly values. These are *not completed counts*.

## Fixed execution / data safety
Private original `Gold data.zip` must match SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. No raw M1 BID/ASK uploaded to GitHub/Actions. One position per annual replay; next observed eligible M1 open no later than 60 seconds after confirmed signal; stop-first when same M1 touches SL and TP; adverse stop gap-through at actual observed opening price; no fabricated minutes; no lookahead. Exactly **$0.40/oz ALL-IN roundtrip**, no second spread deduction. UTC exit-booked monthly P/L and M1 floating marked equity including fee.

## Frozen descriptive gate (NOT proof of edge)
A candidate must have >=80 completed trades in **each** year, >=18/24 strictly positive months, positive annual net in both years, worst of 24 months >=-$20/oz, and each annual floating M1 DD <=$100/oz. Report number passing and all negative results, net/fees/monthly/size/DD and zero-trade executions. Deterministic reference parity samples (>=5/year, including zero-trade if sampled) before marking campaign verified. No refit of candidates on previously exposed 2014–2016; no claims of clean OOS or 12/12 guarantees. Shared-capacity portfolio requires a separate actual joint replay, not summing stand-alone returns. Forward test must be independently frozen with embargo and multiplicity controls.
