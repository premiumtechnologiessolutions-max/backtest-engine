# Frozen arithmetic CLI integration — local evidence (2026-10-30)

**Status:** Research-only. NOT proof of a profitable edge, independent out-of-sample result, broker tick fills, or successful CI on this branch.

## Implemented

The canonical `norisk backtest` CLI now supports `--strategy arithmetic --timeframe M1 --formula-json /local/frozen.json` and either `--execution reference` or `--execution fast`. It uses the existing causal `Formula` / `arithmetic_signals` grammar and canonical fixed **$0.40/oz ALL-IN round-trip** fee.

Formula input is validated **before loading market data**: only a JSON object, no duplicate keys, no NaN/Infinity, no out-of-range/non-finite Formula values, no unknown fields, and a 64 KiB size cap. Non-arithmetic strategies cannot silently accept `--formula-json`. The report persists normalized full Formula parameters and deterministic Formula SHA-256, rather than relying solely on a mutable path.

## Local tests and source parity

* A scoped local Python 3.13 package snapshot passed **57/57 tests** (12 new CLI integration cases plus existing local tests). This is NOT the full GitHub repository test suite or pinned Python 3.12 CI.
* The original private XAUUSD ZIP was verified locally at SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. **The ZIP and source quotes were not uploaded.**
* A predeclared arithmetic **smoke formula** `{"lookback":20,"threshold":0.7,"cooldown":10}` was executed twice against the same 2012 original ZIP M1 slice (352,975 bars): reference and fast engines. Both produced **468 trades**, **-$103.01/oz net**, **$187.20/oz in fees**, **8/12 positive months**, and **one artificial end-of-data liquidation**. No optimization or fresh OOS claim.
* **Exact local parity:** 468/468 trade rows matched across **19 persisted fields**; 12 monthly rows, 53 weekly rows, and 352,975 observed M1 equity rows matched exactly, with zero numeric difference. This checks simulator consistency, not execution realism.
* The official frozen BOS/Fib + H1 annual runner was also **executed locally** on the original 2012 ZIP: **668 trades**, **-$242.85294/oz**, **0/12 positive months**, **$267.20 fees**, accounting reconciled. Its 668-row, 19-column trade CSV was identical to the archived 2012 frozen evidence CSV. This is a repeatability check, NOT independent strategy validation.
* Local attempts to run the larger extracted repository suite reached **200 passed, then a Parquet dependency failure** (`pyarrow` unavailable in the Python 3.13 runtime). An additional filtered run reached 596 passed and one Parquet dependency failure. Neither is a full-suite pass; installing `pyarrow` was blocked by unavailable package-network access.

## Remaining release gates

1. Run full repository tests and pinned Python 3.12 CI on the **new branch head**; no green CI run is claimed here.
2. Run current GitHub HEAD's frozen annual runner and independent replay across all authorized years. The local smoke runs above use core module blobs matching the branch but a local CLI snapshot with fewer preexisting strategy choices.
3. Add the arithmetic strategy to the batch orchestrator only after validating its frozen spec, formula hash, and result reconciliation.
4. Preregister genuinely unseen forward samples, including realistic bid/ask tick stress, before any edge claim.

**Repository visibility:** The GitHub API reported the repository as **public** during this run. No visibility setting was changed; never place private quote data or secrets in this repository. PR #1 remains Draft.
