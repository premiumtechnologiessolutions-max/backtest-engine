# NRF-FAC-014 — Frozen prior-day delayed reclaim, original M1 2012–2013 (2026-10-27)

**Decision: REJECT (preregistered joint gate).** This is a **new causal two-stage prior-UTC-day breakout then later M15 reclaim** family, not another FAC013 wick-sweep parameter retuning. 2012/2013 were already historically exposed. No independent OOS, no guarantee of monthly income, no live trade authorization.

## Frozen provenance and privacy

- Frozen hypothesis and 27,648-spec grid before outcomes at [commit 15b7083](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/15b7083b13b4d434036612b509d189eb742ae339); [spec](FAC014_FROZEN_PRIOR_DAY_DELAYED_RECLAIM_2026-10-27.md). An arithmetic typo in the initial freeze was corrected at this commit **before** the first original-data replay; no parameter choices changed after outcomes.
- Private original `Gold data.zip` verified locally SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. **No raw M1 BID/ASK quotes, detailed trade timestamps, or original ZIP uploaded to public GitHub/Actions.**
- Observed original BID-reference M1 OHLC, complete M15/H1 only, previous eligible closed UTC-day reference, H1 regime from completed candles, IANA-DST sessions. Next observed eligible M1 open <=60s; one 1oz position, stop-first, adverse gap-through, no fabricated fills, fixed exactly **$0.40/oz ALL-IN roundtrip**. M1 floating drawdown includes fee. Each annual replay is separately reset; no merged portfolio P/L.

## Actual executed batch, not theoretical variants

| Metric | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Frozen correlated specs | 27,648 | same IDs | **27,648 distinct** |
| Actually executed annual M1 replays | 27,648 | 27,648 | **55,296** |
| Annual replays with filled trades | 21,504 | 17,920 | **39,424** |
| Zero-trade annual replays (negative controls) | 6,144 | 9,728 | **15,872** |
| Exit-booked monthly values incl. zeros | 331,776 | 331,776 | **663,552** |
| Positive annual-net specs | 6,355 | 4,933 | **1,564 exact IDs positive BOTH years** |
| Distinct causal entry streams | 169 | 163 | correlated, not independent |
| Highest positive-month count per year | 11/12 | 9/12 | **17/24 same ID** |
| Maximum fills for ANY spec | 74 | 67 | frozen >=75/year gate impossible |

- **0/27,648** achieved 24/24 positive months; **0/27,648** reached >=18/24; **0/27,648** passed the preregistered joint gate (>=75 fills/year, >=18/24 positive, annual net >0 both years, worst month >=-$15/oz, annual M1 floating DD <=$100/oz).
- **5,376 specs** had zero trades in both years; do not call all 55,296 annual executions active. These are **27,648 correlated parameter specifications**, not 27,648 independent hypotheses.

## Best post-hoc monthly count (REJECT)

`PDR15_K0.00_W4_FOLLOW_ALIGNED_HOT_ALL_SL1.25_TP1.00` was identified only after the entire grid, and is **not** validated or authorized for retuning.

| Metric | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Positive UTC months | 11/12 | 6/12 | **17/24** |
| Net after fixed fee, $/oz | +18.78875 | -23.33500 | **-4.54625** |
| Filled trades | 63 | 53 | **116** |
| Fees, $/oz | 25.20 | 21.20 | **46.40** |
| Worst UTC month, $/oz | -8.25375 | -17.49375 | **-17.49375** |
| Annual observed M1 floating DD, $/oz | 15.85125 | 31.90875 | **31.90875 max** |

2012 Jan–Dec exit-booked monthly net ($/oz): `[3.37125, 2.93625, 1.0225, -8.25375, 1.95, 3.20625, 0.8875, 0.30375, 2.7, 7.865, 1.86, 0.94]`.

2013 Jan–Dec exit-booked monthly net ($/oz): `[1.975, 1.49125, -1.0225, 2.83125, -17.49375, 7.045, -6.1925, 6.585, -11.47625, 1.485, -4.8875, -3.675]`.

This post-hoc selection loses in 2013 and in the combined years, fails worst-month and trade-count gates. Another configuration has 17/24 but also loses. No rescue tuning.

## Verification, reproducibility and limits

- Independent **local slow M1 state-machine** checked **8 deterministic annual samples**, including first, middle, last and year-highest-month-count. The independent slow engine generated 2,821,168 observed M1 floating equity marks (4 samples × 352,975 in 2012, 4 × 352,317 in 2013), **149 filled trades** across the sampled runs, all 12 monthly values, net, fee, M1 drawdown and expired signals. Maximum audited metric difference **7.1e-15**. The two implementations agree on the aggregate metrics; **per-mark fast/canonical equity equality has not been checked**. This is **NOT** a completed official full-repository `run_fast` canonical parity certification.
- Frozen runner `scripts/batch_prior_day_reclaim_grid.py`, slow independent checker `scripts/verify_fac014_independent_slow.py`, and 5 local synthetic tests `tests/test_batch_prior_day_reclaim_grid.py` were added. **Current-head GitHub Actions status must be checked separately**; do not conflate local 5/5 with full repo CI.
- Private local evidence retains all 55,296 annual parameter outcomes, full 12 monthly P/L each, and aggregate hash manifests. Public GitHub contains only code and aggregate results, not raw quotes or trade timestamp ledgers. No new single-account shared-capacity portfolio was run: **none of these specs passed the preregistered gate**. No independent prospective/embargoed observations yet.

## Negative result / next independent work

Reject FAC014. The new prior-day delayed-reclaim family is sparse and fails the 75-trades-per-year floor even before monthly consistency constraints. Next experiment must be a separately frozen, genuinely different causal hypothesis or fixed-component shared-capacity portfolio; **do not retroactively lower this gate**. Tick BID/ASK and independent forward prospective validation remain open. PR stays Draft/unmerged.