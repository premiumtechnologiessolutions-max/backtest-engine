# NRF-FAC-016 — FROZEN H1/H4 confirmed-swing Fibonacci confluence (2026-10-27)

**PREREGISTERED BEFORE ACCESSING ANY FAC016 ORIGINAL-DATA RESULTS. STATUS: NOT RUN.** This is a new hypothesis family, not a modification of FAC015 or a re-fit of FAC005B/FAC007. No parameter, threshold, or acceptance-gate change after opening results; a bug fix requires a separately identified experiment and complete audit trail.

## Causal hypothesis

On an **observed, fully completed M15** candle, enter in the direction of two **aligned H1 and H4 confirmed pivot swings**, only when its close is near both timeframes' *same* Fibonacci retracement ratio. A pivot at higher-timeframe index j is **not known at j**: it becomes eligible only after exactly w future fully completed, contiguous bars have closed (confirmation timestamp = close of j+w). Strict high/low pivots must exceed/fall below all w neighbors on both sides, with ties rejected. Only the latest known opposite pivot high/low defines each wave. UP = most recently confirmed pivot high was formed after its opposite low; DOWN = most recently confirmed pivot low was formed after its opposite high. Reject ambiguous, invalid, zero-range, nonfinite, or stale swings. The latest wave must have been confirmed <=72h ago for H1, <=336h for H4; the source pivots must be <=168h apart for H1 and <=672h for H4. No fabricated higher-timeframe bars. H1 and H4 must agree on direction. M15 candle body must agree with that direction. All reference prices and medians are known at M15 close.

For UP, retracement price = swing high - ratio*(swing high - swing low). For DOWN, price = swing low + ratio*(swing high - swing low). Both levels must be within tolerance × the **median high-low range of the previous 20 contiguous, completed M15 bars** of the signal candle close. The current candle's range is not used for sizing. Only the most recently confirmed swing on each timeframe is used in FAC016; the broader multi-swing Fibonacci archive is a separate future hypothesis.

## Frozen grid: 18,000 correlated specs/year, 36,000 PLANNED annual replays

- Pivot widths (H1,H4) = [(2,2),(2,3),(3,2),(3,3)] (confirmation after w right-side completed bars).
- Shared retracement ratio = [0.50, 0.62, 0.705, 0.79, 0.87].
- Price confluence tolerance = [0.5, 1.0, 1.5] × previous-20 M15 median range.
- Session = [ALL, LONDON_LOCAL_08_12, NY_LOCAL_0930_1330], IANA DST-aware.
- Stop multiplier and target multiplier each = [0.50,0.75,1.00,1.25,1.50,1.75,2.00,2.25,2.50,2.75] × previous-20 M15 median range.
- **4 × 5 × 3 × 3 × 10 × 10 = 18,000** distinct parameter specifications per year. The 60 distinct pre-execution signal rules are correlated, not independent hypotheses. Planned years 2012/2013 are already exposed design data, never clean OOS.

## Execution, evaluation and refusal gates

Original private `Gold data.zip` SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`, processed locally only. No raw M1 BID/ASK in public GitHub or Actions. Exactly **$0.40/oz ALL-IN roundtrip only**, 1oz, next eligible observed M1 open within <=60s of completed M15 confirmation, one position, stop-first, adverse gap-through, no lookahead or fabricated missing minutes. Report all 12 exit-booked UTC monthly net P/L values per parameter-year, fees, fills, worst month, and observed M1 floating drawdown. Annual reset, no aggregation of standalone strategy profits into an executable portfolio.

**Frozen joint screen:** >=80 fills **in each** design year, >=18/24 strictly positive months, positive annual net in both years, worst UTC month >=-$20/oz, maximum observed annual M1 floating drawdown <=$100/oz. Reject zero-trade or incomplete years from active totals; retain them as negative controls. Require sample canonical `run_fast` and independent slow M1 parity before marking results verified; verify exact-head CI. Never report 18,000 as independent discoveries. Report every negative result. No retuning after rejection, no claimed prospective OOS or 12/12 guarantee. Independent forward validation requires frozen selection, embargo and multiple-testing control.

**At this freeze:** executed annual replays **0**, observed monthly outcomes **0**, canonical samples **0**, candidate acceptance **NOT EVALUATED**. This design commit must precede all FAC016 outcome access.
