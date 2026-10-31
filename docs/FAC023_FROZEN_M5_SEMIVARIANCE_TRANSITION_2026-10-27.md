# FAC023 — Frozen preregistration before any outcomes — M5 signed semivariance transition

**Research ID:** NRF-FAC-023. **Status:** FROZEN_HYPOTHESIS_ONLY; no original-data preflight or P/L opened as of this commit. This is ONE new logical hypothesis, not 2,304 independent hypotheses.

## Exact causal entry specification
- Only fully completed, UTC-aligned M5 candles; require 22 consecutive M5 opens through current candle j (21 intervals), with no market gaps or fabricated bars. At the close of j, compute 12 M5 close-to-close differences d from j-11 through j. U=sum(max(d,0)^2), D=sum(max(-d,0)^2), I=(U-D)/(U+D) when U+D>0. Require finite I at j and j-1.
- Fixed thresholds K={0.25,0.40,0.55}. A bullish event occurs only when I[j]>=K and I[j-1]<K; bearish only when I[j]<=-K and I[j-1]>-K. No repeated signal during a dominance plateau. Entry side is FOLLOW or FADE of that direction.
- Normalized stop/target basis = median(M5 high-low) from **previous 20 fully completed M5 bars**, excluding current j; finite and >0. Signal confirmed at M5 close_at, never earlier. Stop/target distances are basis times frozen multiples.
- H1 gate: last fully completed H1 high-low / median of previous 24 observed completed H1 ranges, gap-aware within 168 hours; H1 age at signal <=60 minutes; require 0<ratio<=2, else halt. CALM if <=1, ACTIVE if >1. Existing DST-aware sessions: ALL, LONDON_LOCAL_08_12, NY_LOCAL_0930_1330. Apply 15-minute per-rule cooldown **after** H1/session gate.
- Grid: K(3) x direction(2) x H1 regime(2) x session(3) = **36 correlated entry rules**. Stop and target multiples each {0.50,0.75,1.00,1.25,1.50,1.75,2.00,2.25}, giving **2,304 correlated parameter specs** and **4,608 planned annual M1 replays** for 2012 and 2013. These years are historically exposed DESIGN, never clean OOS.

## Frozen execution and acceptance
- SHA256 of private Gold data.zip must equal `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Never upload BID/ASK raw prices. Fixed **$0.40/oz ALL-IN roundtrip**; canonical next eligible M1 open <=1 min, stop-first, adverse gap-through, one position per strategy, no lookahead or fabricated minutes.
- Signal-only preflight for SAME entry rule in both 2012/13 must show >=100 potential signals/year; otherwise structurally reject without exit sweep. Signals are not actual fills.
- All joint gates required without retuning: **>=100 actual fills in each year**, **>=18/24 positive exit-booked UTC months**, **annual net positive in both years**, **worst UTC month >= -$20/oz**, **max observed M1 floating drawdown <= $100/oz in each year**. Full fee/month reconciliation, canonical parity samples, independent slow M1 parity, and shared one-slot portfolio simulation required before portfolio claims.
- Do not count a planned run as executed, or correlated specs as independent hypotheses. No 12/12 or live-success claim. Any prospective forward validation requires frozen strategy, embargo and multiple-testing controls; 2012–2016 already exposed.
