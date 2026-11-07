# No Risk FX Quant Lab — frozen research-batch milestone

This addition dispatches existing No Risk FX CLI backtests in a small, deliberate, reproducible sequence. It does **not** claim any historically positive family is a validated live strategy.

## Architecture

- Native No Risk FX engine remains the authority for XAUUSD M1 execution, synthetic fills, all-in costs, and reports.
- A frozen JSON plan explicitly pins **original source-file SHA-256**, full **Git checkout commit**, individual hypotheses and deterministic parameter grids.
- The runner expands up to 50,000 parameter configurations but executes at most 20 by default, or 500 per invocation. It is sequential, not background work.
- Every completed experiment is checked against summary.json, monthly.csv, weekly.csv and trades.csv, its original source hash, M1 quote fingerprint, and Git commit.
- Reports must include every requested calendar month with at least one observed M1 row. It compares P/L, trade count, transaction costs, month counts, and synthetic end-of-data closures. Gaps and synthetic closes remain visible as caveats.
- A static **research_batch_index.html** compares verified research-month results. It never invents curves or independently validated returns. A batch_manifest.json stores the evidence-file hashes.
- On restart, previously accepted reports are audited again; corrupted files, incompatible plan hashes, and incomplete outputs **fail closed**. Previous failures require manual investigation, not silent reruns.

## Private plan format

Keep the plan and raw data **outside the public GitHub repo**; never commit Gold data.zip, full market quotes, user-local paths or trade files. Example only; substitute real immutable hashes and your own local path:

```json
{
  "schema": "NRFX_FROZEN_BATCH_V1",
  "dataset": "/secure/Gold data.zip",
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "engine_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "exposure_context": "historical_exposed",
  "jobs": [
    {
      "id": "ema-smoke-2024",
      "strategy": "ema",
      "timeframe": "M15",
      "execution": "fast",
      "start": "2024-01-01",
      "end": "2024-12-31",
      "parameters": {"fast": 9, "slow": 21, "stop_atr": 1.5, "rr": 2.0}
    }
  ],
  "grids": [
    {
      "id_prefix": "donchian-grid",
      "strategy": "donchian",
      "timeframe": "H1",
      "execution": "fast",
      "start": "2024-01-01",
      "end": "2024-12-31",
      "grid": {
        "donchian_lookback": [10, 20, 30],
        "stop_usd": [10, 15],
        "target_usd": [20, 30]
      }
    }
  ]
}
```

Note the placeholders a/b are NOT actual hashes, and example EMA is a **technical smoke test**, not a promising strategy. The custom limit and QS01 strategies also use allowlisted CLI arguments and strict execution/timeframe rules. VectorBT/OpenBB are not integrated by this increment.

## Usage

Install current checkout per README and confirm a clean working tree.

```sh
python scripts/research_batch_orchestrator.py --plan /secure/research_plan.json --out /secure/research_results --dry-run
python scripts/research_batch_orchestrator.py --plan /secure/research_plan.json --out /secure/research_results --max-jobs 10
```

Open /secure/research_results/research_batch_index.html locally. To resume an incomplete but otherwise valid batch, run **the exact same command with the exact same original file, plan and Git commit**. The next 10 unexecuted jobs will run; existing completed entries are revalidated, not re-executed.

## Boundaries and failure policy

- Canonical model: fixed **$0.40/oz all-in per round trip**, exactly **1 oz research quantity**. Do not add another spread/fee on top.
- The canonical model uses synthetic OHLC reference fills; slippage, variable real spread, broker fills, margin, VPS and live MT5 integration are **not verified** here.
- The listed windows are historically exposed; none is classified clean prospective out-of-sample (OOS).
- Choosing the highest monthly score after thousands of parameter trials can severely overfit. A result merely passing report reconciliation is **not a strategy deployment gate**.
- Per-calendar-month realized net P/L is based on EXIT timing; floating equity can differ. Missing or incomplete sessions, unusual quote gaps and forced end-of-data exits require separate review.
- Code/dataset hashes tie the output to declared inputs. They do not prove economic or execution validity. Keep original private source and logs outside public GitHub.

## Verification

```sh
python -m pytest -q tests/test_research_batch_orchestrator.py
python -m pytest -q
```

Regression tests rely on **synthetic** reports and mocked subprocess calls. A successful test suite does not establish historical source replay, profitability or market execution. A separate CI smoke check uses invented Gold-shaped M1 candles to run the real CLI; still not authorized user data.

This isolated draft branch is intended to merge into feat/quant-engine-foundation **after** code review, tests and checks. It does not itself close the main Quant Engine Draft PR #1 or certify deployment.
