# Signal-only joint-ID preflight — 2026-10-27

**Process improvement, not a new strategy/backtest/OOS result.** Before an SL/TP profitability sweep, a frozen family can be ruled out if *no same frozen parameter ID* has at least the required number of causally generated signals in **every** required design year. A one-fill-per-signal execution cannot fill more trades than it has signals. The previous max-per-year test is weaker: two different IDs can independently exceed the threshold in different years while no single ID qualifies across both.

`scripts/preflight_signal_capacity.py` accepts **signal-only** CSVs with `id`, `signals`, and frozen rule columns, **without trade counts, P/L, M1 quotes, or exit outcomes**. It fails closed on malformed counts, missing/duplicate IDs, changing ID-to-rule mappings across years, or changed signal counts across risk-exit variants. It emits only aggregate counts; no IDs or private quotes. Its prerequisite is genuinely pre-execution, causal signal counts under a preregistered grid. Do not retrospectively describe a preflight as preregistered.

Usage, on locally generated private signal-only evidence (not GitHub Actions):

```bash
python scripts/preflight_signal_capacity.py \
  --year-csv 2012 /private/signals_2012.csv \
  --year-csv 2013 /private/signals_2013.csv \
  --rule-columns h4_window excursion retreat regime session \
  --min-fills 100
```

**Historical negative control:** Applying only the signal-count columns from the previously completed FAC018 2012/2013 candidate exports reproduced `STRUCTURALLY_UNREACHABLE`: 9,216 correlated specs, 144 rule groups/year, maximum 39 and 29 signals/year, zero frozen IDs with >=100 signals in both years. This is a *posthoc* replay of an arithmetic bound, **not** a new 2012/2013 backtest or a changed FAC018 rejection. The 2012/2013 years are exposed, not clean OOS.

**Synthetic counterexample:** 2012 can have max 110 signals for rule A and 2013 max 110 for rule B, yet the intersection of IDs meeting >=100/year is empty. The joint-ID test correctly rejects where per-year maxima alone would not.

**Factory totals unchanged:** 590,380 active annual backtests, 7,084,560 active monthly P/L cells, zero new strategy hypotheses, zero new canonical M1 parity samples. A non-rejection only means the necessary count gate is not disproved; it does not prove fills, positive months, shared-capacity feasibility, risk limits, tick parity or prospective performance. Fixed $0.40/oz ALL-IN, one-position shared capacity, original market data private, PR #1 Draft/unmerged. No live orders, billing/privacy changes, or raw-data uploads.
