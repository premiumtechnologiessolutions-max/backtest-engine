# FAC007 — locked FAC005B candidate fails chronological 2014–2016 stress (2026-10-26)

**REJECT the candidate, no parameter modifications.** This result follows the [pre-result frozen evaluation criteria](FAC007_LOCKED_FAC005B_2014_2016_FOLLOWUP_2026-10-26.md) committed at `d84c2622b4d6e354867f3498820cd7b979cb8c9a` **before** inspecting 2014–2016 outcomes. We did NOT optimize any setting after opening the results.

## Fixed original hypothesis
Selected from FAC005B's exposed 2012–2013 design research: `RANGEH1_EMA15_F08_S72_G1.00_SL6.50_TP1.00` — complete M15 EMA8/72 recross gated by latest closed H1 relative realized range >=1.0 versus the preceding 24 complete H1 bars. Fully closed causal signal; first eligible M1 open <=60 sec; 1 ounce, max 1 position, fixed SL $6.50, TP $1.00, **$0.40 USD/oz ALL-IN roundtrip only**. No added spread, commission or hypothetical slippage. Stop-first in ambiguous M1 and adverse quote-gap opening prices.

Source was the original **private** `Gold data.zip` (SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`), used **locally only**, no BID/ASK M1 data uploaded to public GitHub. Algorithm sourced from CI-verified FAC005B source snapshot originally used for frozen batch evaluation.

### Genuine additional full-year original-source replays

| Year | M1 observations | Closed trades | Months with positive booked net | Net USD/oz after costs | Total fees | Max observed M1 floating DD |
|---|---:|---:|---:|---:|---:|---:|
| 2014 | 351,794 | 27 | **8/12** | **-$6.30** | $10.80 | $20.58 |
| 2015 | 353,772 | 41 | **6/12** | **-$12.90** | $16.40 | $19.76 |
| 2016 | 354,246 | 50 | **5/12** | **-$30.00** | $20.00 | $35.80 |
| **Sum of separately reset yearly runs** | — | **118** | **19/36** | **-$49.20** | **$47.20** | **Do not sum DD** |

In each of the **three full-year replays**, canonical `norisk_quant.execution.run` and accelerated `norisk_quant.fast_engine.run_fast` matched all exported trade fields (numerical tolerance 1e-7) **and every observed one-minute equity mark exactly** (maximum equity error 0). All 12 monthly CSV entries per year reconcile to year P/L. Exact loaded M1 SHA-256 fingerprints retained privately, with the original gold source SHA authenticated.

**Frozen pass criteria were >=30/36 positive months, positive net in EACH year, >=20 trades per year and annual M1 marked drawdown <=$30/oz.** It failed positive-month rate, year profits, and the 2016 DD cap. **Therefore reject unchanged candidate as a monthly-profit hypothesis.** Even a 21/24 result on selected years cannot justify promoting it.

### Interpretation and artifacts
2014–2016 follow 2012–2013 chronologically for this fixed model, but earlier broad No Risk FX research examined parts of those dates; therefore label this **historically exposed chronological follow-up, NOT globally clean independent OOS**. Candidate was already selected after seeing the earlier years. BID-reference OHLC does NOT replicate actual broker tick spreads/fills or true tradable P&L; years are separately reset, not one financed five-year account.

Private reproducibility bundle `NoRiskFX_FAC007_Locked_FAC005B_2014_2016_Rejection_2026-10-26.zip` contains 36 monthly rows, annual JSON summaries, actual executed trade ledgers, the locked specification, original-source fingerprints and the offline replay script, **but not raw quote history**. No live trading recommendation.

**Next:** Do not retroactively tune this weak-sample fee-sensitive winner. Expand to *different*, preregistered causal families and use a frozen prospective walk-forward holdout or paper-trading feed for meaningful validation. Keep Draft PR unmerged.
