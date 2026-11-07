# Frozen annual sensitivity: observed calendar-month gate — 2026-10-26

## Finding

The official `scripts/run_bos_fib_frozen_sensitivity.py` previously declared
`sampled_months = 12 * len(years)` without checking whether every requested
calendar month contained even one M1 observation. The annual JSON ZIP member
and requested calendar year could both exist while a whole month was absent.
A resulting report could therefore claim a twelve-month sensitivity sample
that had only eleven or fewer observed months.

This is distinct from the earlier **missing annual ZIP/Parquet partition**
gates. It also does not certify minute-level coverage or broker sessions.

## Change

- Strictly validate frozen runner year selections as actual Python integer
  years within 2010–2026; reject booleans, floats, NaN and strings.
- Before signal generation, demand sorted, unique UTC timestamps belonging
  exclusively to the selected year, with **at least one observed M1 candle
  in every one of its 12 calendar months**. Fail closed if a month is absent.
- After writing the standard reports, assert that the monthly ledger has
  12 rows and that `months_observed` and
  `months_with_m1_observations` are both 12.
- Add synthetic regression cases for January/June/December omissions,
  wrong-year timestamps, invalid indexes, invalid year types and early
  rejection before strategy generation or report writing.

## Important limitation

**Twelve observed months are necessary but NOT sufficient for a complete
year.** A single quote per month would pass this specific gate. Missing
minutes, feed outages, holidays, source authentication, bid/ask broker
execution and final-month partial coverage require separate evidence.
No strategy settings, fill ordering, fees or historical profit/loss
results were changed.

## Verification status

- A **reconstructed isolated copy** of the new validation functions was
  checked with synthetic Pandas data on Python 3.13: **16/16 local scoped
  cases passed**. This is NOT a run of the actual imported GitHub module.
- New repository tests were committed but **have not passed a complete
  current-head pytest or installed-package test run**.
- The authorized original Gold data.zip was unavailable in this runtime;
  the official frozen runner and the actual 13-field independent ledger
  replay remain unexecuted on this head.
- GitHub Actions CI remains unverified under the October quota constraint;
  do not enable paid minutes, change billing, or turn on push/PR triggers
  without an infrastructure confirmation.

Keep private PR #1 Draft. No raw market data uploaded, no live trading,
no claim of profitable strategy or clean out-of-sample validation.
