# NRF-FAC-018 — FROZEN session-inventory unwind / H4 path-efficiency (2026-10-27)

**PRE-OUTCOME REGISTRATION. STATUS: NOT RUN at this freeze.** This is one new hypothesis family with 9,216 *correlated* parameter specifications per year, not 9,216 independent hypotheses. Design years 2012/2013 are historically exposed and NOT independent OOS. No parameter is to be tuned after seeing these years.

## Economic hypothesis (distinct from prior factories)

The London or New York morning session can accumulate one-sided intraday inventory relative to its own **time-weighted typical-price anchor**, then unwind part of the deviation when the higher-timeframe H4 price path is inefficient/sideways. This is *not* VWAP (no volume available), not FAC012 compression breakout, FAC013 stop sweep, FAC014 prior-day reclaim, FAC015 autocorrelation, FAC016 Fibonacci or FAC017 two-bar shock.

For each actual observed **completed** M15 bar j, and the preceding completed bar j-1, require an uninterrupted 15-minute sequence from the **exact local session start**. London: 08:00–12:00 Europe/London; New York: 09:30–13:30 America/New_York (DST-aware). Reject any missing M15 bar, late session start, or non-UTC timestamp; no synthetic minutes. Require j close strictly before session end, so next eligible M1 open can occur inside the session.

At the j close, compute anchor A as the unweighted mean of typical prices (high+low+close)/3 for completed session bars **from the session start through j-2**, excluding both j-1 and j. Require at least two bars in this anchor. Use a positive median M15 high-low baseline B from the **20 contiguous bars ending j-2** (excluding both event bars); the stop/target normalization base R is the median of the 20 contiguous completed M15 ranges ending j-1 (excluding j). An excursion occurs when |close(j-1)-A| >= k*B. Confirmation at j requires a candle body directed back toward A and a retreat >= r*|close(j-1)-A| while still on the original side of A. Short after upper excursion, long after lower excursion. No signal before j closes. One signal per j.

Use only completed H4 closes: for H4 window N, efficiency E = |close(last)-close(first)| / sum(abs(consecutive close differences)) over the last N **contiguous** H4 bars. Denominator must be >0. Last H4 close <= signal close, age 0..4h. RANGE: 0<=E<=0.35; TRANSITION: 0.35<E<=0.65. **HALT** if E>0.65, stale, missing, nonfinite, or denominator zero. This halt uses only pre-known information.

## Immutable Cartesian grid

- H4 efficiency lookback N = [4, 8, 12].
- Previous-bar anchor excursion multiple k = [1.00, 1.50, 2.00, 2.50].
- Inward retreat fraction r = [0.25, 0.40, 0.55].
- H4 regime = [RANGE, TRANSITION].
- Session = [LONDON_LOCAL_08_12, NY_LOCAL_0930_1330].
- Stop and target multipliers independently = [0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25] * R.
- **3 x 4 x 3 x 2 x 2 x 8 x 8 = 9,216 correlated specs/year; 18,432 planned annual executions across 2012/2013; only 144 pre-execution signal-rule combinations.**
- No extra optimization, adaptive threshold tuning, unlisted session, or alternative fees allowed in this batch.

## Execution and preregistered joint screen

Private original Gold data.zip SHA256 **1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121** must match locally. One ounce, one active position, exactly **$0.40/oz ALL-IN roundtrip**, next observed eligible M1 open <=60 seconds after M15 confirmation or expire, stop-first on same M1 bar, adverse gap-through, no lookahead, no invented M1. Report 12 UTC exit-booked monthly net P/L values per year, annual net, actual fills, expired signals, fees, worst month, maximum *observed M1 floating* drawdown, and zero-trade counts. Canonical run_fast sample parity and independent reference engine checks are required before any certification.

**Frozen joint acceptance:** >=100 fills in EACH year; >=18/24 strictly positive UTC months; positive net in BOTH years; worst monthly P/L >= -$20/oz; annual maximum observed M1 floating drawdown <=$100/oz. A parameter that passes design screening remains exploratory and must NOT be called OOS or deployable. Any portfolio requires a separate *actual one-position shared-capacity* replay; standalone P/L must never be summed. Prospective evaluation must preregister a fixed choice, embargo, multiple-testing correction, and new observations not used in discovery.

At freeze: **0 FAC018 annual backtests, 0 observed monthly P/L, 0 parity samples, 0 passing candidates**. Public GitHub receives only code, tests, docs and aggregate metadata; never raw M1 BID/ASK, ZIP, quote/trade ledgers. PR remains Draft, unmerged, no billing/privacy or live trading.
