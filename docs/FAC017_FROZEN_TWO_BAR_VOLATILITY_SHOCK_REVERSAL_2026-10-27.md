# NRF-FAC-017 — FROZEN two-bar volatility-shock exhaustion reversal (2026-10-27)

**PRE-OUTCOME FREEZE. STATUS: NOT RUN.** The original private Gold data.zip is not accessible in this run. Do not label planned grid executions as completed, and do not infer outcomes. This family is distinct from single-candle wick rejection (FAC003), Donchian fade (FAC002), lag-one sign autocorrelation (FAC015), and Fib confluence (FAC016). All 2012/2013 data are historically exposed, never independent OOS.

## Hypothesis and causal event

At the close of observed, fully completed M15 bar j, inspect **previous bar j-1** as a large directional displacement shock. Its high-low range must be >= shock_multiple times the median of the preceding N fully completed, contiguous M15 bar ranges **j-N-1 ... j-2** (exclude shock and signal bars). The shock's close must lie in the extreme 20% of its own range (upper 20% for bullish shock, lower 20% for bearish shock), and its body must agree with shock direction. Current completed bar j must reverse and close through a specified fraction of the shock range, but not beyond the opposite shock extreme; its body must oppose the shock. Short after an upward shock, long after a downward shock. A shock cannot be reused by a later signal. Every lookback must be fully contiguous at 15-minute spacing; never synthesize bars across overnight/weekend gaps.

The risk-normalization base is the median of the **previous 20 fully completed M15 ranges** relative to signal bar j (exclude j). It must be positive and finite. This is a two-bar *exhaustion/reversal* mechanism, not a wick-only or moving-average signal.

Apply only last **completed** H1 volatility regime, with H1 range divided by median of its previous 24 observed H1 ranges, provided 24 historical H1 observations are within 168 elapsed hours. No need for 25 contiguous H1 bars, because the original source is gap-affected. H1 information must have close timestamp <= M15 signal close and age <=3600s. QUIET means ratio <=1.0; ACTIVE means 1.0 < ratio <=2.0 (2.0 is a pre-known volatility halt). DST-aware sessions: ALL, London 08:00–12:00 Europe/London, New York 09:30–13:30 America/New_York.

## Exact frozen grid

- Previous-range baseline N: [12,20,32,48].
- Shock-range multiple: [1.25,1.50,2.00,2.50].
- Opposite retracement threshold of shock range: [0.25,0.40,0.55].
- H1 regime: [QUIET,ACTIVE].
- Session: [ALL,LONDON_LOCAL_08_12,NY_LOCAL_0930_1330].
- Stop and target each: [0.50,0.75,1.00,1.25,1.50,1.75,2.00,2.25] times previous-20 M15 median range.
- **4 x 4 x 3 x 2 x 3 x 8 x 8 = 18,432 correlated parameter specs per year; 36,864 annual parameter replays PLANNED for 2012/2013; zero executed at freeze.** At most 288 distinct pre-execution signal-rule combinations, not 18,432 independent hypotheses.

For upward shock: close(j-1) >= low(j-1)+0.8*range(j-1), close(j)<open(j), low(j-1) <= close(j) <= high(j-1), and close(j) <= high(j-1)-retracement*range(j-1). For downward shock: close(j-1) <= low(j-1)+0.2*range(j-1), close(j)>open(j), low(j-1) <= close(j) <= high(j-1), and close(j) >= low(j-1)+retracement*range(j-1). Shock body strictly directional. No signal before j close. Entry at next observed eligible M1 open <=60s after confirmation, otherwise expire.

## Execution and preregistered rejection

Exactly $0.40/oz ALL-IN roundtrip **only**, 1 oz, single-position annual replay, stop-first if SL/TP touched in same M1 bar, adverse opening gap-through stop, no fabricated M1, UTC exit-booked 12 monthly P/L points, fees = $0.40 x filled trades, worst month, M1 floating max drawdown, expired signals, zero-trade counts, signal-stream hashes. No summing independent equity curves as if they were a shared-capacity portfolio.

**Frozen joint acceptance screen:** >=100 filled trades in **each** year; >=18/24 strictly positive UTC months; both annual nets >0; worst month >=-$20/oz; annual M1 floating max drawdown <=$100/oz. Require fast vs canonical samples and independent slow M1 ledger/equity verification before any acceptance claim. Record negative outcomes and zero-trade runs, and refuse retroactive tuning. Later 2014–2016 data are also exposed; forward/prospective evaluation requires an immutable selection, embargo, multiple-testing controls and newly collected observations.

Original private ZIP must SHA256 match `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. **NEVER upload BID/ASK/M1 source, detailed ledgers or the original ZIP to this public repository or GitHub Actions.** PR remains Draft, no billing/privacy changes, no live trading.

**Freeze counts:** 0 actual FAC017 backtests, 0 observed monthly P/L values, 0 verified parity samples, 0 candidate passes. No claim of 12/12 or guaranteed monthly profitability.
