# No Risk FX — Reproducible Quant Grid + Batch Runner v1

Status: opt-in, local research orchestration. NOT live trading, independently validated OOS performance or guaranteed profitability. The two modules call the existing No Risk FX CLI; they do not replace it.

## Components

- scripts/research_grid.py: expand frozen EMA/Donchian parameter axes (at most 20,000 raw combinations), reject invalid/duplicate configurations, and write SHA-256-identified plans containing up to 50 candidates each. A specification is a correlated parameter configuration, NOT an independent discovered strategy.
- scripts/research_batch.py: validate one plan, show exact commands without execution by default, and only when --execute is supplied, run canonical NRFX CLI backtests. It refuses an incorrect source ZIP SHA-256, a changed or dirty engine checkout, invalid parameters, wrong output provenance, missing/duplicate months, conflicting P/L totals and output overwrites.
- tests/test_research_grid.py and tests/test_research_batch.py: synthetic regression coverage; tests do NOT certify real market replay.

## Example frozen grid (JSON)

The placeholder absolute paths, hashes and Git commit below MUST be replaced with the correct local source and checked-out immutable code version. Never upload your original Gold ZIP to this public repository.

    {
      "schema": "NRFX_GRID_V1",
      "source": "/secure/Gold data.zip",
      "source_sha256": "REPLACE_WITH_64_HEX_SOURCE_FILE_SHA256",
      "engine_commit": "REPLACE_WITH_40_HEX_COMMIT",
      "start": "2012-01-01",
      "end": "2013-12-31",
      "grids": [
        {
          "id_prefix": "EMA15",
          "strategy": "ema",
          "timeframe": "M15",
          "execution": "fast",
          "axes": {
            "fast": [7, 9, 12],
            "slow": [21, 34],
            "stop_atr": [1.0, 1.5],
            "rr": [1.5, 2.0]
          }
        },
        {
          "id_prefix": "DONCH_H1",
          "strategy": "donchian",
          "timeframe": "H1",
          "execution": "reference",
          "axes": {
            "donchian_lookback": [15, 20, 25],
            "stop_usd": [10.0, 15.0],
            "target_usd": [20.0, 30.0]
          }
        }
      ]
    }

Save this JSON as a local grid-spec file. Paths/hashes shown above are intentionally invalid so that nobody accidentally claims a verified run using placeholder data.

## Commands

    python -m pytest -q tests/test_research_grid.py tests/test_research_batch.py

    python scripts/research_grid.py --grid /secure/grid_spec.json --out /secure/frozen_grid_001

    python scripts/research_batch.py --plan /secure/frozen_grid_001/batch_00001.json --out /secure/batch_run_001

The preceding batch command is a **dry run**. It validates and prints planned commands but executes no backtests and writes no results. Actual local evaluation must be explicitly requested:

    python scripts/research_batch.py --plan /secure/frozen_grid_001/batch_00001.json --out /secure/batch_run_001 --execute

A successful batch creates a batch_manifest.json and monthly_comparison.csv. If any experiment fails, the batch is marked FAILED and does not publish a combined comparison. The original private source remains on the local machine. The output reports USD per ounce of gold with fixed $0.40 per ounce ALL-IN roundtrip cost for the research reference model.

## Validation boundaries

A full calendar month in the requested date range does NOT establish uninterrupted broker data. The exported monthly flags explicitly separate merely having any M1 data from period completeness. Gaps, same-bar ambiguity, synthetic end-of-data exits and broker-specific Bid/Ask execution are not solved here. No strategy tested on already explored historical data should be labeled independent OOS. Run prospective validation and independent execution parity separately.

Grid expansion itself is quick but replaying many M1 candidate years is computationally substantial; limit candidate count to available compute. No schedule or cloud resources are provisioned by these scripts. Batch plans are versioned against exact source and Git code, and results must be treated as preliminary research until verification.

This increment is intentionally kept on a separate branch to avoid collisions with concurrent Quant Engine research. Do not merge into main or deploy to live trading until full tests and acceptance gates pass.
