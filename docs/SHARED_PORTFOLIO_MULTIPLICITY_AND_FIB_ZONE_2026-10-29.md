# No Risk FX — Shared Portfolio + Search Multiplicity Research (2026-10-29)

## Scope and scientific status

This implementation creates an **auditable synthetic OHLC research pathway** for
combining several candidate families on the same underlying XAUUSD M1 clock.
It does **not** sum independent per-strategy equity curves, cannot validate a
live broker/tick fill, is not independent OOS, and provides no guarantee of a
profitable month.

Code:
- `scripts/run_frozen_portfolio_mix.py` — frozen original-source, pinned-code runner
- `src/norisk_quant/portfolio_unified.py` — pre-existing shared Market+Limit execution
- `src/norisk_quant/search_multiplicity.py` — exact shared-year sign-flip maxT diagnostic
- `scripts/research_cross_year_candidate_screen.py` — training-only cross-year candidate screen

Tests:
- `tests/test_frozen_portfolio_mix.py`
- `tests/test_search_multiplicity.py`
- `tests/test_research_cross_year_candidate_screen.py`
- `tests/test_bos_custom_fib_zone_factory.py`
- `tests/test_tf_sweep_dual_wick_boundary.py`

## 1. Frozen shared-portfolio contract

The runner accepts a strict JSON plan with:
- schema `NRFX_FROZEN_SHARED_PORTFOLIO_V1`
- absolute private original Gold ZIP path, SHA256 exactly
  `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`
- current clean full Git commit `engine_commit`, completed UTC start/end dates
- `historical_exposed` only
- 1–8 explicit strategy/timeframe/parameter components

Supported component families: `m1-sweep`, `tf-sweep` (M15 or H1),
`bos-fib` (M1 Limit), `fvg` (M1/M5/M15/H1/H4 Limit). Components share a
**single slot and maximum 1 oz**; signal/order collisions use the
already-existing deterministic causal unified execution policy. Stops take
precedence over targets when M1 OHLC ordering is ambiguous; adverse opening
gaps, deferred same-entry-bar Limit targets and expired orders follow the
unified engine policy. Fixed **all-in roundtrip cost $0.40/oz** applies once
per actually executed trade. No additional fee is layered on.

Example *plan shape* (not runnable until actual absolute private file path and
40-character pinned code revision replace the placeholders):

```json
{
  "schema": "NRFX_FROZEN_SHARED_PORTFOLIO_V1",
  "dataset": "/PRIVATE/GOLD/Gold data.zip",
  "source_sha256": "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121",
  "engine_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "start": "2012-01-01",
  "end": "2012-12-31",
  "exposure_context": "historical_exposed",
  "components": [
    {"strategy": "m1-sweep", "timeframe": "M1",
     "parameters": {"sweep_lookback": 20, "sweep_reward_risk": 1.5}},
    {"strategy": "tf-sweep", "timeframe": "M15",
     "parameters": {"tf_sweep_lookback_bars": 12}},
    {"strategy": "bos-fib", "timeframe": "M1",
     "parameters": {"bos_fib_entry": 0.87, "bos_zone_lower": 0.50,
                    "bos_zone_upper": 0.87}},
    {"strategy": "fvg", "timeframe": "H1",
     "parameters": {"fvg_min_gap_usd": 0.5}}
  ]
}
```

Only after freezing a real private plan, the runner's entry point is:

```bash
python -m scripts.run_frozen_portfolio_mix --plan /private/frozen-mix.json --out /private/new-research-run
```

The runner rejects unexpected fields, unapproved source SHA, changed checkout,
future/non-historical windows, invalid component parameter sets, duplicate
strategy/timeframe components, symlinked source/output, missing whole UTC M1
calendar months and an output directory that already exists. Reports are
written in a private temporary directory before being published; a failed
run must not publish an accepted report.

The output contains `trades.csv`, `monthly.csv`, `weekly.csv`,
`equity_m1.csv`, `summary.json`, `evidence.json`. Each report file's
SHA256, the source ZIP SHA, loaded M1 BID/ASK fingerprint, parameter
resolutions, code commit, signal counts and capacity constraints are recorded.
The original source ZIP and raw quotes are **not** copied to GitHub or into
published outputs.

## 2. BOS/Fibonacci zone compatibility fix

The factory had advertised five custom Fibonacci levels: 0.50, 0.62, 0.705,
0.79 and 0.87. However, the BOS constructor's historical defaults were a
0.618–0.786 zone, which rejected 0.50, 0.79 and 0.87 at execution time.

The CLI now supports optional `--bos-zone-lower` and
`--bos-zone-upper`, with the **unchanged original defaults** 0.618/0.786.
The *new* factory's exploratory BOS grids explicitly specify
`bos_zone_lower=0.50` and `bos_zone_upper=0.87` so all five requested
levels are executable. Frozen spec validation enforces
`0 < zone_lower <= fib_entry <= zone_upper < 1`; unrelated strategies
cannot silently accept changed BOS-zone options.

The generator still defines 228 variants per completed year and 3,192
unexecuted annual specifications for 2012–2025 (14 completed years). The
defined counts are not executed historical tests and must not be reported
as profitable candidates.

## 3. Train-only multiplicity diagnostic

The existing cross-year screen groups identical frozen parameters across
annual runs. On a **complete** annual candidate universe it additionally
calculates one-sided, self-normalized, exact sign-flip tests based on **training
year totals only**:

`T_i = sum_y(PnL_iy) / sqrt(sum_y(PnL_iy^2))`, with zero-norm mapped to
zero. All `2^Y` sign vectors for Y in [2,16] are enumerated; the same
year-level sign flips are applied to every candidate, preserving candidate
dependence **under the hypothetical joint symmetric null**. Single-step
maxT family adjusted tail fractions are recorded along with unadjusted
fractions. Review years are excluded entirely from the diagnostic.

**Critical limitation:** the joint sign symmetry/exchangeability assumption
is NOT verified for financial returns; year blocks can be dependent, the
candidate set has a lengthy historical search history, and the training data
was heavily inspected. Therefore these are **diagnostics, NOT valid
independent inferential p-values**, not a false discovery guarantee, not an
OOS certificate and never a promotion/live-trading gate. The screen's
ranking still uses training-only heuristic metrics and review is descriptive.
If any annual competitor result is missing, adjusted fractions and
candidate ranks are withheld, not computed on the first finished subset.

## 4. Verification boundary as of this commit

- Original private Gold ZIP is **not available** in the present runtime.
  No new original-source SHA-pinned 13-field execution replay has been run.
- Locally, 69 selected older-core-plus-new-module tests passed, and 40
  planned BOS/Fibonacci parameter combinations were accepted by the actual
  `BosFibSettings` constructor. These are not full latest-head suite results.
- Synthetic shared-capacity core tests verified one market trade with
  $0.40 fee, then market-vs-FVG-Limit same-minute contention with one
  rejected limit due to frozen shared capacity. No real broker execution.
- The exact current GitHub HEAD, new runner tests, installed pinned Python
  3.12 environment, and GitHub Actions remain **unverified green**; the
  available local mirror lacks the entire latest GitHub tree and pyarrow.
- Previous historically exposed BOS/H1 results remain negative. No fresh
  unsearched validation years have been certified.

**Release gates:** complete HEAD pytest/CI on pinned dependencies, exact original
Gold ZIP 13-field replay, full-year source coverage and quote-gap audits,
run real private frozen research batches, validate shared portfolio
performance with genuinely untouched prospective data and observed broker
execution constraints. PR #1 remains Draft/unmerged. Do not change repo
visibility, costs, billing, or upload private raw quotes.
