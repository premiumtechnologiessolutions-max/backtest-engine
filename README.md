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

**Current status:** no live tick-fill engine, portfolio capital ledger, distributed
optimizer or remote ChatGPT runner exists yet. The GitHub Actions runner probe
also failed without reaching a usable diagnostic log; CI has NOT passed.

## Code review workflow

Open the PR from feat/quant-engine-foundation into main after GitHub Actions pass. Subsequent strategies should be separate PRs and use the same frozen execution/fee/data-quality conventions.

GitHub is the code and report registry, NOT itself a live backtesting compute server or a data warehouse. ChatGPT conversations can inspect connected repositories; launching executions from chat requires a separate supported runner/workflow connector.
