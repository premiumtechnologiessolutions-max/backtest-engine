# NRF-FAC-010 — FROZEN robust-MAD recovery + H1 regime + UTC session (2026-10-26)

**PREREGISTERED BEFORE ANY FAC010 ORIGINAL-SOURCE OUTCOMES WERE OPENED.** New, separately tagged exploratory family; 2012/2013 historically exposed design, not clean OOS. FAC008 (independent ticks) and FAC009 (shared portfolio) retain their existing registry meanings.

## Causal signal definition
- Build only *fully observed*, epoch-aligned M15 candles from actual BID M1 bars; never synthesize missing minutes. Split at any M15 timestamp gap; rolling statistics may not bridge gaps.
- For each completed M15 bar at time t, calculate prior-only rolling **median** and median absolute deviation (MAD) of the preceding W **completed** M15 closes. Robust z(t) = (close(t) - median_prior)/(1.4826 * MAD_prior); skip zero/nonfinite MAD. Both z(t-1) and z(t) must have a full W-bar same-contiguous-segment baseline.
- **Long recovery**: z(t-1) <= -K and z(t) > -K. **Short recovery**: z(t-1) >= +K and z(t) < +K. Confirm at M15 close, not candle open.
- For each M15 confirmation, join the most recent fully completed H1 bar (age 0..60 elapsed minutes), whose H1 range divided by the median of its previous 24 observed complete H1 ranges (current excluded) is finite. Oldest baseline H1 close must be within 168 elapsed hours. Regime filter: QUIET <=0.85, QUIET <=1.15, or HOT >=1.15. These are distinct *precommitted* gates.
- UTC confirmation-hour session filter: ALL (0..23), EU_FIXED_UTC (07..14), or US_FIXED_UTC (13..20). These are deliberately UTC windows, NOT DST-sensitive New York local time or claims about official exchange opens. No lookahead.
- W = [12,20,32,48]; K = [1.25,1.75,2.25,2.75]; regime gates = [QUIET0.85, QUIET1.15, HOT1.15]; session = [ALL, EU_FIXED_UTC, US_FIXED_UTC].
- Stop distances in USD/oz = [1.00,1.50,2.00,2.50,3.00,3.50,4.00,4.50,5.00,5.50,6.00,6.50]; target distances = [0.50,1.00,1.50,2.00,2.50,3.00,3.50,4.00,4.50,5.00,5.50,6.00]. **144 entry-rule parameterizations × 144 exit variants = 20,736 distinct parameter specs per annual replay**, 41,472 annual replays planned, NOT 20,736 independent hypotheses.
- Entry at first observed M1 open at/after confirmation only if <=60 seconds old; 1 oz and at most one active position per independently reset year; stop-first on same M1 bar, adverse opening gap-through stops, no same-bar replacement after closing. Exactly **$0.40/oz ALL-IN roundtrip only**, no extra modeled spread or slippage; BID-reference OHLC is NOT a broker-tick fill model.
- Exit-booked UTC monthly net; include all 12 calendar months, zero-trade months as nonpositive. Report gross, total fees, trade count, net, worst month, M1 marked-equity peak-to-trough drawdown and expired signals. No fabricated M1 marks.

## Predeclared acceptance and falsification
- Descriptive ranking only; no inference of clean OOS. A **screening** configuration must achieve >=18/24 positive months, net >0 in EACH 2012 and 2013, >=50 trades in EACH year, worst month >=-$20/oz across 24 months, and max observed M1 DD <=$100/oz in EACH year. These are screening gates, NOT guarantees or multiple-testing-corrected evidence.
- Report every zero-trade and negative result, exact number executed, number of distinct signal streams per year, positive months, worst month and max DD. Retain every completed configuration result locally. Never silently re-grid this experiment or retrofit a winner.
- Validate at least 3 deterministic parameter samples per year against **canonical norisk_quant.fast_engine.run_fast** on original private source; compare all 12 months, executed count, fees, net and M1 floating DD within 1e-7; ideally also reference run() trade ledger and full marked equity. Any mismatch blocks acceptance and registry completion.
- A portfolio must be replayed with genuinely shared capacity before making combined-profit claims. Independently reset years are not a continuous funded account.
- Source is original private `Gold data.zip`, SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. NEVER commit raw BID/ASK quotes, archive, or trade-level price samples to public GitHub/Actions.
- Chronologically later 2014–2016 have already been examined by this project; no selected historical period is independent OOS. Future forward prospective protocol requires embargo and multiple-testing control.
