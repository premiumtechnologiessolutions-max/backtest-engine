# FAC022 — Frozen M5 directional path efficiency with completed H1 volatility halt
Date: 2026-10-27 UTC. **PRE-OUTCOME preregistration**; status FROZEN, no P/L inspected for this family.

## Distinct causal hypothesis
The signed efficiency of a **six-completed-M5-bar** price path (30 minutes) may distinguish persistent displacement from noisy reversion. This is one related hypothesis family, not 2,304 independent hypotheses. It differs from FAC021's cumulative reset-on-threshold CUSUM, FAC020's lagged variance ratio, and H1 directional runs. The choice of window/thresholds/filters below is fixed before reading FAC022 outcomes.

## Signals, data and causality
Aggregate only genuinely present, contiguous UTC M1 into complete M5 and H1 bars; never fabricate missing minutes. At the **completed** M5 close j, require at least 20 previous contiguous complete M5 bars and six consecutive close changes. Define d_i=C_i-C_(i-1) for i=j-5,...,j, D=sum(abs(d_i)), E=abs(C_j-C_(j-6))/D, and S=sign(C_j-C_(j-6)). Abstain if D<=0, S=0, nonfinite data, or a missing/partial bar in the 20-bar history. A threshold crossing is **E>=K** (not a posthoc optimum). Use previous 20 M5 high-low ranges (j-20 through j-1), median B_j>0, to normalize SL/TP distances; no current or future range in B_j. FOLLOW trades S; FADE trades -S. Per frozen rule, at most one signal every 30 minutes (events at completed M5 closes, skip if t-last_emitted<1800 seconds). Cooldown is applied before execution; actual overlapping trades remain subject to the canonical engine's one-position capacity. 

At signal timestamp use only the last completed H1 bar, close_at<=signal time and age<=3600 seconds. H1 ratio = last completed H1 range / median of its previous 24 observed complete H1 ranges within 168 hours. CALM: 0<ratio<=1, ACTIVE: 1<ratio<=2; ratio>2 or stale/missing context HALTS. Sessions: ALL, Europe/London 08:00–12:00 local, America/New_York 09:30–13:30 local; timezone database DST. Entry is next eligible observed M1 open <=60 seconds; canonical stop-first, adverse gap-through, no same-bar fill, no lookahead.

## Frozen grid and preflight
- Path length 6 M5 changes (fixed), prior 20 contiguous M5 ranges (fixed), 30-minute signal cooldown (fixed).
- Efficiency K: [0.55, 0.70, 0.85]; direction: [FOLLOW, FADE]; H1 regime: [CALM, ACTIVE]; session: [ALL, LONDON_LOCAL_08_12, NY_LOCAL_0930_1330].
- Stop multipliers: [0.50,0.75,1.00,1.25,1.50,1.75,2.00,2.25]; target multipliers same. Distances in USD/oz = B_j * multiplier.
- **36 correlated signal-rule groups × 64 exits = 2,304 parameter specs/year; 2012+2013 = 4,608 PLANNED annual M1 replays**. Not 4,608 independent hypotheses. No post-outcome grid expansion.
- Signal-only same-rule preflight first: if no same rule has >=100 events in BOTH exposed years, reject as structurally infeasible before any exit-grid execution. If feasible, execute the complete frozen grid, no selective exit pruning.
- Frozen joint gate: >=100 filled trades in EACH year, >=18/24 strictly positive UTC exit-booked months, net >0 in EACH year after exactly $0.40/oz ALL-IN roundtrip, worst UTC month >=-$20/oz, observed M1 floating drawdown <=$100/oz in EACH year. Zero fills do not count as active.
- Verify fee and monthly accounting, canonical run_fast samples, independent slow reference full trade ledger and floating M1 marks. Any portfolio requires actual shared capacity; never add standalone profits.

## Interpretation / constraints
Private original Gold data.zip SHA256 1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121; raw BID/ASK and M1 remain LOCAL ONLY, never GitHub or Actions. 2012–2016 historically exposed; not clean OOS. Multiple-testing penalties, embargoed prospective forward data, independent tick BID/ASK spread/slippage checks and shared-capacity portfolio are prerequisites for any deployment claim. No billing/privacy changes, no live trades. PR #1 stays Draft/unmerged.
