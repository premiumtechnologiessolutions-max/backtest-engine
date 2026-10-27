# FAC021 — Frozen M15 signed CUSUM displacement with completed H1 volatility gate
Date: 2026-10-27 UTC. **Pre-outcome registration**. Status: FROZEN / NOT YET REPLAYED.

## Independent research hypothesis
A path-dependent, signed cumulative displacement of **completed** M15 close-to-close moves, normalized by the median of the **previous 20 completed M15 high-low ranges**, may produce a regime-transition entry signal. Unlike FAC020's two-step variance ratio, FAC017's single/two-bar shock reversal, or FAC018's H4 session inventory, this is a stateful sequential threshold crossing with explicit reset. This is ONE logical hypothesis family, not thousands of independent hypotheses.

## Exact causal signal
Aggregate only actually observed contiguous UTC M1 bars into complete M15/H1 bars; never fill missing minutes. On any M15 discontinuity reset both CUSUM accumulators and require 20 earlier contiguous complete M15 ranges before a new signal. At completed M15 bar j, compute B_j = median(high-low of bars j-20,...,j-1), and z_j=(close_j-close_{j-1})/B_j. If B_j<=0 or nonfinite, reset and abstain. Maintain P_j=max(0,P_(j-1)+z_j) and N_j=min(0,N_(j-1)+z_j). A crossing P_j>=K or N_j<=-K produces one event at bar j's **close_at** timestamp; reset both accumulators immediately. The event direction is +1 for P crossing and -1 for N crossing. FOLLOW takes event direction, FADE reverses it. No data after event time is used.

H1 gate: last completed H1 bar close_at <= event time, at most 3600 seconds old; ratio = its high-low divided by median ranges of its prior 24 observed completed H1 bars, with prior 24 within 168 hours. CALM means 0<ratio<=1; ACTIVE means 1<ratio<=2; **ratio>2 or stale/unavailable H1 => halt**. Session gate ALL / Europe-London 08:00–12:00 / America-New_York 09:30–13:30, evaluated from event UTC instant with timezone database DST rules. Event order and timestamps are immutable. Entries next eligible observed M1 open <=60s; stop-first and adverse gap-through per canonical execution; no same-bar fills.

## Frozen grid (no posthoc expansion)
- M15 prior-range lookback: [20] (fixed).
- CUSUM thresholds K: [1.5,2.5,3.5].
- Signal direction: [FOLLOW, FADE].
- H1 prior-range history: 24 (fixed); H1 regimes: [CALM,ACTIVE].
- Sessions: [ALL,LONDON_LOCAL_08_12,NY_LOCAL_0930_1330].
- Stop multipliers: [0.50,0.75,1.00,1.25,1.50,1.75,2.00,2.25].
- Target multipliers: same 8 values. Stop/target USD/oz distance = B_j * multiplier.
- 3 × 2 × 2 × 3 = **36 correlated signal-rule groups/year**; 36 × 8 × 8 = **2,304 correlated parameter specs/year**; two exposed years 2012/2013 = **4,608 planned annual replays**, NOT 4,608 independent hypotheses. This grid is fixed regardless of preflight outcomes.

## Pre-outcome gates and verification
1. Original private Gold data.zip SHA256 **1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121**. Never upload raw quotes, ZIP, or private ledger to public GitHub.
2. Signal-only preflight for same rule IDs in 2012 and 2013; if none has >=100 eligible signals in EACH year, mark structurally unable to pass >=100 fills/year and do NOT run exit grid. Do not relax or retune.
3. Frozen joint acceptance: >=100 filled trades EACH year; >=18/24 strictly positive UTC exit-booked months; net >0 EACH year after exactly $0.40/oz ALL-IN roundtrip; worst month >=-$20/oz; observed M1 floating drawdown <=$100/oz EACH year. A 24/24 historical result, if any, is NOT clean OOS.
4. Run frozen 2,304-spec grid per year only if signal preflight passes. Validate annual and monthly fee arithmetic, canonical run_fast full trade/mark parity samples, and independent slow reference for representative cases. Test shared-capacity portfolio separately; never sum standalone strategies as executable profits.
5. 2012–2016 already historically exposed; no prospective success claim. Forward evaluation needs preregistered untouched future data, embargo, multiple-testing controls and independent broker tick/spread checks.

No billing/privacy changes, no live trading, PR #1 stays Draft/unmerged.
