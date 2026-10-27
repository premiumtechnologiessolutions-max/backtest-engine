# NRF-FAC-015 — preregistered M15 lag-one sign autocorrelation fade (2026-10-27)

**FROZEN BEFORE ORIGINAL-DATA OUTCOMES.** Hypothesis: when the most recent *observed, contiguous, completed* M15 candle closes and its last N completed candle-body directions exhibit low lag-one Pearson sign autocorrelation, fade the final candle's direction (not RSI, wick sweep, Donchian, prior-day reclaim, directional run, or compression breakout). Gate using the last **completed** gap-aware H1 range divided by the median of its previous 24 observed completed H1 ranges, with maximum H1 age 60 minutes. Local sessions are Europe/London 08:00–12:00 and America/New_York 09:30–13:30 (IANA DST); ALL is also allowed.

**Frozen 36,000 correlated specifications per year (72,000 planned annual executions across 2012/2013):**
- Sign-correlation rolling lengths N = [8, 12, 16, 24, 32], computed only on N contiguous observed M15 candles with nonzero bodies; Pearson correlation between N-1 paired lagged signs, variance-zero windows ineligible.
- Correlation upper bounds = [-0.4, -0.2, 0.0, 0.2]; condition correlation <= bound.
- Last-bar absolute body / prior-20-completed-M15 absolute-body median lower bound = [0.5, 1.0, 1.5], prior 20 bars must be contiguous and median >0.
- H1 range regime = [CALM (last closed H1 range / prior24 median <=1), ACTIVE (>1)]; no interpolation of missing hours, require 24 observed completed H1 bars within 168h, with last H1 at most 3600s before signal.
- Sessions = [ALL, LONDON_LOCAL_08_12, NY_LOCAL_0930_1330].
- Stop and target = each [0.5,0.75,1.0,1.25,1.5,1.75,2.0,2.25,2.5,2.75] times the *previous-20 completed M15 high-low median*, measured at signal close. All combinations 5×4×3×2×3×10×10 = **36,000** per year. A parameter specification is **not** an independent statistical hypothesis.

**Execution contract:** exact original private ZIP SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`; no raw BID/ASK to GitHub or Actions. M15 close-confirmed signal; next observed eligible M1 open <=60s, one 1oz position, no lookahead, stop-first, adverse gap-through, no fabricated missing minutes, exactly **$0.40/oz ALL-IN roundtrip** (no additional fee), UTC exit-booked monthly P/L, observed M1 floating DD incl. fee. Annual resets; no portfolio aggregation.

**Frozen joint acceptance gate:** >=100 filled trades **in each year**, >=18/24 strictly positive months combined, annual net >0 both years, worst UTC month >= -$20/oz, maximum observed annual M1 floating drawdown <=$100/oz. Report 24 monthly values for every parameter, both years, zero-trade negative controls, fees, DD, number of genuinely distinct signal streams, and independent slow/canonical parity samples. Do not relax criteria or retune rejected candidates post hoc. 2012–2016 are historically exposed design years, NOT clean OOS. No trading/live guarantee. Independent prospective evaluation requires preregistered forward split, embargo, and multiplicity control.

**Status at preregistration:** NOT RUN; zero executed replays, zero monthly outcomes, no claimed validation.