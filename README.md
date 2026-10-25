# No Risk FX Quant Engine

**Status: v0.1 research foundation — NOT a validated trading engine.**

A single reproducible XAUUSD backtesting foundation. Private repository. No live trading, no orders, no guaranteed monthly profit.

## What is implemented today

- Annual JSON ZIP ingestion for the historical XAUUSD BID/ASK M1 format (ts,o,h,l,c,ao,ah,al,ac,v).
- Strict UTC candle timestamp semantics; original prices are never overwritten.
- Per-year Parquet partitions and SHA-256 source ZIP manifest. Invalid BID/ASK OHLC years are quarantined instead of silently repaired.
- Data quality counts: missing intervals, large gaps, quote inconsistencies.
- Conservative next-open, no-lookahead, single-position M1 execution kernel.
- Round-trip **ALL-IN fixed $0.40 per ounce**: 0.01 lot = 1 oz *if* broker contract is 100 oz/lot. No variable spread, commission, or slippage is charged on top.
- Carry a position through missing M1 data; adverse first-available-open stop fills. When both TP and SL are in the same M1 candle, assume SL first.
- Reproducible CSV weekly/monthly reports, trade ledger, M1 marked equity, drawdown and JSON summary.
- One EMA-crossover plug-in to smoke-test the architecture (not a recommended strategy).
- Automated unit tests and GitHub Actions quality checks.

**Not done:** accurate broker-specific fill replay, true tick reconstruction, full ICT/SMC/FVG catalogue, complete floating-equity path through missing time, portfolio allocation, published evidence of profitability, remote one-click ChatGPT-run integration. Existing legacy backtests are NOT imported as validated results.

## Install (Python 3.11+)

Clone this private repo in a trusted Python environment:

    git clone https://github.com/premiumtechnologiessolutions-max/backtest-engine.git
    cd backtest-engine
    python -m venv .venv
    .venv\Scripts\activate
    python -m pip install -e ".[dev]"
    python -m pytest -q

On macOS/Linux, activate with: source .venv/bin/activate

## Verified first real-data audit (2019 only)

The read-only audit script has been executed against the original 2019.json inside the local Gold data.zip (not uploaded to GitHub):

    python scripts/audit_gold_zip.py --zip "C:\path\Gold data.zip" --year 2019 --out 2019_audit.json

Result: 353,320 M1 records; no duplicate timestamps or Bid/Ask OHLC anomalies; 258 intervals over 10 minutes. Common gaps of 61–62 minutes (196) and 2,941–2,942 minutes (47) are consistent with daily and weekend market closures. See docs/audits/xauusd_2019_source_audit_2026-10-25.json. This is a **source data check**, not a passing backtest.

**CI blocker:** GitHub Actions jobs have repeatedly failed before any runner steps started (empty runner name and steps). No pytest success has been established; see docs/CI_STATUS_AR.md. Keep PR #1 in draft.

## New: fast research backtests directly from the original ZIP

The engine now includes a fast M1 replay path and an H1 Donchian 20-bar
research variant (fixed $15 XAUUSD stop, $30 target, **not** classic
Turtle 20/10). Original source-year JSON can be selected directly out
of the private ZIP, with no user-facing Parquet conversion prerequisite.

    norisk backtest --data "/secure/Gold data.zip" --start 2024-01-01 --end 2024-12-31 --strategy donchian --timeframe H1 --donchian-lookback 20 --stop-usd 15 --target-usd 30 --execution fast --ounces 1 --all-in-cost-per-ounce 0.40 --out reports/generated/donchian-2024

For research regression, change `--execution fast` to
`--execution reference` and compare trades and marked equity.
Two engine implementations are NOT considered equivalent until parity
tests pass. `--strategy ema` remains an EMA/ATR experimental smoke
strategy, and is not the same stop/target specification as the separate
2024 EMA standalone validation.

An **independent standalone script** ran the continuous 2020–Sep 20
2026 Donchian variant on **2,381,928 M1** and produced 1,334 trades,
**48/81 profitable months** and **+$1,146 per ounce** net with fixed
all-in costs. This does NOT certify that the GitHub implementation
produces exactly the same fills, or that the strategy is independently
profitable. See
`docs/REAL_DATA_SMOKE_AND_READINESS_2026-10-25.md`.

GitHub Actions on the private repo currently **fails before receiving a
runner** (independent probe job `runner_id=0`, `steps=[]`).
This is tracked as Issue #2. PR #1 remains **draft/unmerged**.

## Verified GitHub Actions account-level quota blocker — 2026-10-25

Confirmed from GitHub's official owner-account notification emails:
**2000/2000 included Actions minutes** reached 2026-10-04 and
**0.5/0.5 GB Actions storage** reached 2026-10-08.
Both alerts say included usage renews **2026-11-01**.

Evidence: runner-only probe and normal CI jobs failed before starting
(`runner_id=0`, `steps=[]`), which is consistent with the
GitHub-hosted runner billing/quota gate. The current account's
spending budget has not been read/modified.

**Action taken:** while the free quota is exhausted, both
`.github/workflows/ci.yml` and `runner-probe.yml` are
**temporarily manual-dispatch-only** to prevent dozens of failed
PR/push runs and emails. Auto PR triggering will be restored once a
runner probe actually passes after the GitHub quota reset.

No payment method, spending limit, or repository visibility was
changed. No user-market-data ZIP was pushed to GitHub. Keep PR #1
as a draft until unit tests have passed for this code revision.
See [tracking Issue #2](https://github.com/premiumtechnologiessolutions-max/backtest-engine/issues/2).

## Research audit progress: actual historical ledger matching

A local reconstructed Limit replay was checked against **3,800 archived
historical XAUUSD trades** (H1 BOS/Fibonacci, with and without 5× projected
reward-to-fee screen) for **2012–2019**. Each entry, exit, timestamp,
direction, SL, TP, profit, fixed $0.40/oz cost, reason and gap count
matched across **13 fields**; 16 year/model combinations were checked.
**This is NOT a full-suite GitHub CI pass**, and the reconstructed local
modules were not all byte-identical to the current repository.
See `docs/LIMIT_3800_TRADE_PARITY_AUDIT_2026-10-25.md`.

A new `scripts/verify_bos_h1_parity.py` replays the **actual imported
repository package** against external standalone reference ledgers and
**fails closed** on mismatched values. Both the raw gold archive and
historical reference ledgers must be supplied in a private authorized
execution environment; neither is committed to GitHub.
`tests/test_historical_parity_contract.py` verifies its drift detection.
Additional randomized M1/Limit stress fixtures run without market data.

**New data provenance guard:** every `norisk backtest` CLI report
records `source_fingerprints.loaded_m1_bidask_sha256` for **exact UTC
timestamps and 8 BID/ASK price columns**, plus the file SHA if supplied,
row count, selected strategy CLI parameters and any available CI commit
revision. If no code revision is available, the report explicitly says
an immutable Git commit and locked dependencies are still needed for
exact reproducibility. A dataset fingerprint alone cannot prove broker
execution quality. This detects stealth changes to a single quote or
timestamp without publishing raw prices.

## Execution causality hardening

The fast M1 runner previously shortened exact confirmation timestamps to
integer epoch seconds. For a signal confirmed at `00:01:00.500Z`, this
could incorrectly permit entry at the `00:01:00` candle OPEN — before
the signal existed. The optimized engine now compares **nanoseconds**
against observed UTC M1 openings. The reference and optimized engines
both reject source minute timestamps with any sub-minute offset and
nonfinite OHLC prices. Position/fee/stop/target values reject NaN and
Infinity. See `tests/test_subsecond_causality_and_quote_guards.py`.

These fixes are committed but the entire GitHub Actions suite remains
**not yet run** because the private account's October Actions quota is
exhausted. Local independent historical matching on 3,800 entries is
encouraging but cannot replace green checks on the immutable repo
commit, the exact data and the full historical scenario pipeline.

## Long-session safety / BOS-Fib full monthly sensitivity — Oct 25 2026

The engine has two **opt-in**, separately versioned, causal safety
choices for the M1 BOS/Fibonacci strategy:

- `--bos-h1-max-age-minutes 120` (with `--bos-require-h1-trend`):
  rejects orders relying on a stale H1 EMA trend after long closures.
  Default `None` preserves the older archived 3,800-trade parity.
- `--bos-ignore-dual-pivots`: ignores a minute candle that is both
  a high and low 3/3 pivot (unknown intrabar order). This can alter
  downstream structure and is **not** simply subtracting bad trades.

Run the frozen four-year protocol with the **actual package** and a
private original ZIP (no upload to Git):
```sh
python scripts/run_bos_fib_frozen_sensitivity.py \
  --gold-zip "/secure/Gold data.zip" \
  --years 2012 2017 2020 2024 \
  --out "/secure/reports/bos-h1-safety"
```

The offline scoped 24-unit-test run passed. The standalone full M1
replay of this exact fixed rule set returned respectively **-$242.85,
-$129.69, -$387.99 and -$465.70 per ounce**, with **0/12 positive
months in each sampled year** (2,876 trades). Every year's completed
trade/monthly ledger and fee matched; the report is
`docs/LONG_SESSION_BOS_H1_EXECUTION_SAFETY_2026-10-25.md`.
These four exposed years were NOT a continuous portfolio or unseen OOS,
and the standalone calculations are NOT a new full-GitHub-CI pass.
Do not deploy this rejected variant.

Canonical CLI backtests now reject `--all-in-cost-per-ounce` values
other than **0.40** to protect results from accidentally omitting
transaction costs. Signal confirmation also requires explicit timezone
information. No raw gold data is stored in the repo.

## Ingest data (LOCAL ONLY, do not upload raw ZIP to Git)

Put your original annual JSON archive outside the repository or in the ignored data directory:

    norisk import-gold "C:\path\Gold data.zip" --out data/processed

This creates per-year Parquet partitions, a manifest with SHA-256 of the source archive, and per-year quality metrics. **Any year with quote anomalies is not imported**, and needs manual investigation, not automatic "fixes."

## Run the first engine smoke backtest

    norisk backtest --data data/processed --start 2020-01-01 --end 2020-12-31 --timeframe M15 --ounces 1 --all-in-cost-per-ounce 0.40 --out reports/generated/ema-smoke-2020

Generated files:

- trades.csv: each executed trade, fee, exit reason, gap exposure.
- weekly.csv and monthly.csv: periodized realized profits and losses (including months with no trades).
- equity_m1.csv: sampled realized + open-position P/L; gaps are unobservable.
- summary.json: run parameters, aggregate P/L, total fees, win rate, profit factor and drawdown.

The default demo strategy is an EMA crossover **purely to verify plumbing**. Its historical returns should not be used as an investment recommendation.

## Execution limitations you must understand

1. This first release uses original BID OHLC as a **common research reference quote for both directions**, and one synthetic round-trip $0.40/oz cost. It is not a claim that buys/sells fill at BID with a broker. ASK is preserved for quality assessment, not separately charged.
2. An M1 OHLC candle does not disclose whether the SL or TP was reached first; the engine assumes SL first.
3. Normal closures and missing feeds both create time gaps; the engine cannot reconstruct ticks inside these gaps. Positions remain open; stale entry signals expire.
4. Weekly/monthly realized profit is assigned to **exit** date. Open equity and intraday exposure require separate inspection. Final close of an unfinished run is simulated and marked end_of_data.
5. An imported partial final month (e.g., September 2026) must be marked **partial**, not interpreted as a full calendar month.
6. 2020–2026 has been repeatedly inspected in older experiments and is **not a clean out-of-sample test** for newly tuned strategies. New independent forward data are required for validation.

See docs/RESEARCH_PROTOCOL_AR.md for development gates.


## Audit gaps from imported historical data

After running `norisk import-gold`, classify observed quote gaps *without* assuming they were all exchange closures:

    norisk audit-gaps --data data/processed --start 2010-01-01 --end 2026-09-20 --min-missing-minutes 10 --out reports/generated/gap-audit

Files generated:
- `gap_catalogue.csv`: UTC and New York timestamps, missing minute counts, provisional class, confidence, and holiday-calendar hints.
- `gap_manual_review.csv`: unusual or holiday-adjacent intervals requiring source-provider verification.
- `gap_summary.json`: gap totals and category counts for the requested data version and period.

The `regular_daily_break_pattern` and `regular_weekend_pattern` labels mean the **timestamps** match typical trading hours; they do NOT verify the broker feed's past schedule. US holiday hints are likewise **candidates**, not confirmed closures or events. The classification uses America/New_York and handles daylight-saving transitions.

**Important:** This new command cannot be run by GitHub with only code present; the original private historical data must be available to an authorized execution environment. No market-data ZIP is committed to the repository.

## GitHub Actions status

GitHub Actions checks are **not confirmed passing** as of 2026-10-25. Both the regular `Engine quality gates` workflow and a separate runner-only probe (no checkout/pip/tests) reported failure. Available connector responses contained no per-step logs, so the root cause **is undiagnosed** and neither failing CI nor passing unit tests may be inferred. Keep the PR in draft; do not merge until diagnostics and an independent test run are successful.


## BOS + Fibonacci Golden Zone from supplied M1 chart (research)

Implemented as a **causal M1 structure/limit-order strategy**, not a promise
that an image pattern is profitable. Source:
`src/norisk_quant/bos_fib.py` and `tests/test_bos_fib.py`.

    norisk backtest --data "/secure/Gold data.zip" --start 2024-01-01 --end 2024-12-31 --strategy bos-fib --timeframe M1 --bos-fib-entry 0.618 --bos-rr 1.0 --bos-pivot-left 3 --bos-pivot-right 3 --bos-stop-buffer-usd 0.10 --bos-min-break-usd 0.10 --bos-min-impulse-usd 1.0 --bos-expiry-minutes 120 --ounces 1 --all-in-cost-per-ounce 0.40 --out reports/generated/bos-fib-2024

Fixed meaning: rising two confirmed highs/lows or falling two confirmed
highs/lows, BOS when a completed minute closes beyond a confirmed
structure level, retracement limit at 0.618 from the anchored impulse,
SL beyond anchor, TP 1R and only the first two BOS events in the same
detected trend regime. The extra three M1 candles needed to confirm a
pivot are never used before they close. Golden Zone is 0.618–0.786;
`--bos-fib-entry 0.705` chooses a deeper entry, and `--bos-rr 1.5`
tests the alternate TP. These are **explicit mechanical interpretations**
of the handwritten strategy, not universal ICT rules or actual Elliot waves.

**CORRECTION (2026-10-25):** The earlier BOS/Fib standalone P/L numbers in
`docs/BOS_FIB_M1_2026-10-25_FIXED_RESEARCH.md` are **superseded**:
the old M1 limit simulator sometimes credited a take-profit inside its
**entry candle** without knowing whether that price printed before
the entry limit filled. The new conservative limit simulator defers TP
until a later observed M1 candle; stop-first remains. This is still an
OHLC scenario and cannot reconstruct tick order.

Under the corrected fill model, the 2024 BOS/Fib baseline has
**2,284 trades, -$1,020.33/oz net and 0/12 winning months**.
Predeclared fee coverage filters may be tested with
`--bos-min-gross-reward-fee-multiple 5` or `10` (0 means disabled).
They require planned gross target >=5×/10× fixed $0.40 all-in fee;
this uses entry and TP values already known at BOS close.

From a 15-year **standalone** real-data study (2012–Sep 2026),
the 5× filter was **-$57.03** in 2012–16 development,
**+$2.96 from just 19 trades** in 2017–19 chronological check,
and **-$1,236.98** in already-examined 2020–Sep26 history.
No filter qualifies as a strategy with dependable monthly returns.
See `docs/BOS_FIB_COST_GATE_AND_ENTRY_BAR_TP_CORRECTION_2026-10-25.md`.
None of these results certifies Github-package backtest parity, true
tick-level fill accuracy or independently unseen out-of-sample profits.

## Strict H1 confirmation filter (research, NOT validated profit)

Optional BOS/Fib gate requiring a **fully observed H1 bar (60/60 M1)**
to have closed on or before the BOS signal; close must be on the same
side of EMA50 as the trade, and EMA50 must slope that direction relative
to five previous completed H1 bars. Unfinished H1 bars never count.

    norisk backtest --data "/secure/Gold data.zip" --start 2012-01-01 --end 2012-12-31 --strategy bos-fib --timeframe M1 --bos-require-h1-trend --bos-fib-entry 0.618 --bos-rr 1 --ounces 1 --all-in-cost-per-ounce 0.40 --out reports/generated/bos-fib-h1-2012

Add `--bos-min-gross-reward-fee-multiple 5` for the second frozen
cost-coverage candidate. Both **failed** historical acceptance:
`h1_only` returned 0/60 months and -$1,133.61/oz in 2012–16,
0/36 and -$440.20 in 2017–19. `h1_and_5x` returned 5/60 months and
-$24.88 (42 trades), then 1/36 and -$5.85 (4 trades). Year-by-year
standalone replay audited 16 ledgers against weekly/monthly P/L, with
8/8 local H1 and BOS generator checks passing. This is NOT proof of
whole GitHub package parity or real-tick broker execution.
Source and constraints: `docs/BOS_FIB_H1_REGIME_REJECT_2012_2019_2026-10-25.md`.

## Experimental limit-order strategy support (FVG midpoint)

The engine now has an **M1 OHLC limit-order research mode** to avoid
misrepresenting every Fair Value Gap as an immediate market entry.

Example (original BID/ASK ZIP stays private):

    norisk backtest --data "/secure/Gold data.zip" --start 2024-01-01 --end 2024-12-31 --strategy fvg --timeframe H1 --fvg-min-gap-usd 0.5 --fvg-stop-buffer-usd 0.1 --fvg-rr 2 --fvg-expiry-hours 20 --ounces 1 --all-in-cost-per-ounce 0.40 --out reports/generated/fvg-h1-2024

The generator uses three **consecutive, complete** H1 candles, defines
the gap from first/third candle ranges, and places a **limit order at
50% of the gap (CE)** after third-candle close. Buy SL is beyond the
first candle's low; sell SL beyond its high. Target is the configured
reward/risk multiplier and order expiry is elapsed clock hours.

When both limit entry and SL are inside an M1 candle, the simulator
assumes SL was hit after entry: this is intentionally conservative,
**not proof of actual event order**. Opening beyond SL gets a worse
first-available-open price; normal fills use the limit price with
no assumed favorable improvement. Only one position is allowed and
other pending orders are discarded upon fill; this is **not** portfolio
execution. This experimental model lacks ICT-specific displacement,
BOS/CHoCH, sessions or tick replay until expressly added.

Reports run the fixed-all-in cost and accounting integrity checks and
explicitly mark **end_of_data** forced exits and separate weekly/monthly
realized PnL from sampled equity changes. GitHub CI is still failing
before runner assignment, so the newly committed files and tests are
not yet a fully certified executable release.

## Target: research platform beyond the MT5 Strategy Tester

The goal is a **stronger auditable research workflow**, not an unsupported claim
of superior price-fill realism or speed. MT5 already supports real broker ticks,
multi-symbol testing, genetic optimization and distributed agents. With only M1
data, our core is strictly less precise than a calibrated MT5 real-tick replay.

Added early research components:
- `src/norisk_quant/ticks.py`: checks external genuine-looking timestamped
  Bid/Ask quote ticks, their SHA-256 fingerprint, and M1 coverage. It **does
  not replay tick orders** or independently authenticate a broker feed.
- `src/norisk_quant/walkforward.py`: embargoed walk-forward fold planner;
  automatically labels no historical split as proven independent.
- `src/norisk_quant/registry.py`: stable experiment identity (data SHA,
  full Git commit, rules, parameters, timeframe, exposure and fixed fee).
  A saved identity is **not** evidence a backtest actually ran.
- `docs/MT5_PARITY_AND_SUPERSET_GATES.md`: benchmark checklist, current
  feature gaps, precise acceptance gates and mutually exclusive cost scenarios.

Commands:

    norisk plan-walkforward --start-year 2012 --last-year 2024 --min-training-years 5 --embargo-days 14 --out reports/generated/folds.json
    norisk audit-ticks --csv /secure/broker_ticks.csv --provider "Broker source" --out reports/generated/tick-audit.json
    norisk identify-experiment --spec configs/experiment.json --out reports/generated/experiment-manifest.json

**Current status:** a shared-capacity market/Limit M1 research portfolio equity ledger
exists, but it is **not** a broker capital/margin model. No live tick-fill engine,
distributed optimizer or remote ChatGPT runner exists yet. The GitHub Actions runner probe
also failed without reaching a usable diagnostic log; CI has NOT passed.

## Code review workflow

Open the PR from feat/quant-engine-foundation into main after GitHub Actions pass. Subsequent strategies should be separate PRs and use the same frozen execution/fee/data-quality conventions.

GitHub is the code and report registry, NOT itself a live backtesting compute server or a data warehouse. ChatGPT conversations can inspect connected repositories; launching executions from chat requires a separate supported runner/workflow connector.


## Shared LIMIT portfolio and exact-core parity (2026-10-25)

- `src/norisk_quant/portfolio_limits.py`: causal multi-strategy LIMIT replay with
  shared exposure, one $0.40/oz roundtrip cost, stop-first ambiguity and
  gap-through handling. Use `write_limit_portfolio_report` for weekly/monthly
  and observed M1 equity reports.
- `tests/test_portfolio_limits.py`: nine local-passed deterministic checks.
- `scripts/verify_portfolio_limit_2024.py`: private-data-only 2024 fixture parity;
  requires the original ZIP locally; never commit that ZIP.
- `docs/CENTRAL_LIMIT_EXACT_PARITY_AND_PORTFOLIO_2026-10-25.md`:
  exact GitHub module SHA verification and 3,800 historical BOS/H1 trades
  matching independent archived ledgers. **Both BOS/H1 variants remain rejected**.
  Full GitHub Actions CI is still blocked and PR #1 remains Draft.

## Unified Market + Limit execution and frozen QS01 design screen

`norisk_quant.portfolio_unified.run_unified_portfolio(minutes, signals, orders,
settings)` runs both instruction types against one `PortfolioSettings` allocation
and one realized/floating equity ledger. `write_unified_portfolio_report` writes
trade, minute equity, weekly and monthly ledgers. Every closed trade pays exactly
$0.40 per ounce once; open marks reserve that full roundtrip fee.

Opening Market instructions compete with already marketable Limits by
confirmation time, strategy name and input order. Limits requiring a later
intrabar touch use only the remaining capacity. Existing and newly consumed
slots stay reserved through that minute, even after an exit. Limit entry-bar
targets are deferred; ambiguous stop/target bars stop first. Limits receive no
favorable opening improvement, while adverse opening gaps stop at the first
observed price. Limit expiry uses observed bar openings and does not establish
the ordering of a touch versus an expiry inside a minute.

An optional positive-integer `max_holding_minutes` is supported by the central
reference/fast Market engines and unified portfolio. At the first observed open
at/after the cap, an already breached stop/target takes precedence, followed by
the time exit, before that minute's later high/low. Legacy portfolio and single
Limit entry points reject the option explicitly.

The report coverage fields expose whole missing weeks/months. Their closing mark
and allocated equity change remain unknown; the first resumed mark has a
separately labeled change since the last observed period. No price is filled in.

Private-data acceptance and design-only commands:

    python scripts/verify_unified_real_m1.py --json /private/2024.json --out /private/unified-acceptance
    python scripts/research_qs01_design.py --source-dir /private/annual-json --out /private/qs01-design

The first command compares reference/fast Donchian ledgers, sparse mixed execution
fixtures against standalone engines, every observed floating mark from original
M1 closes, constrained capacity, and weekly/monthly totals. Fixture returns are
execution diagnostics. The second command exposes no year or threshold tuning
arguments: it loads 2012–2016 only and applies the preregistered QS01 screen once.
The original preregistration remains unchanged; extracted annual file identities
are recorded separately if the original ZIP is unavailable.
