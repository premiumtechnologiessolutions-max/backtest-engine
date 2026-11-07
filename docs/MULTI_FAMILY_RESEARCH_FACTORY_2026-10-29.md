# No Risk FX — Multi-Family Quant Research Factory, 29 Oct 2026

## What is now implemented

- M1 price/liquidity sweep and reclaim: src/norisk_quant/liquidity_sweep_m1.py; causal, gap-aware, dual-sweep rejection, vectorized detector; execution through CLI strategy m1-sweep (reference and fast).
- M15/H1 higher-timeframe sweep: src/norisk_quant/liquidity_sweep.py, integrated into CLI as tf-sweep with settings and fast/reference market engines.
- Both families registered in scripts/research_batch_orchestrator.py with strict timeframe and numeric parameter gates.
- Reproducible design generator: scripts/generate_quant_research_grid.py, creates deterministic historical-exposed research definitions for M1 sweep, M15/H1 sweep, BOS/Fibonacci (levels 0.50, 0.62, 0.705, 0.79, 0.87), and FVG. It does not execute trading, create a broker connection, or reveal raw source quotes.
- Research candidate screening from the prior changes: scripts/research_candidate_screen.py. Candidate ranking uses training results only; later comparison is descriptive and explicitly NOT certified independent OOS.

## Scale and preregistration boundaries

Each COMPLETED historical year has 228 parameter specifications:
- M1 sweep 144; M15/H1 sweep 36 combined; BOS/Fibonacci 40; FVG 8.
- The safe default uses 2012–2025 (14 completed years) = 3,192 historical-exposed definitions, 84 parameter grids.
- Including full calendar year 2026 would create 3,420 definitions over 2012–2026, but 2026 is incomplete as of 29 Oct 2026. The plan freezing gate rejects an ongoing/future full year. This is why the safe default excludes 2026.
- A definition is NOT an executed backtest, not 3,192 independent hypotheses, and not 3,192 verified strategies. The factory executor remains deliberately bounded to a maximum 500 actual jobs per invocation and requires an original private source ZIP.

Dry-run locally: python -m scripts.generate_quant_research_grid --dry-run

For actual plan freezing, the tool requires a private original ZIP, exact SHA-256 1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121, a clean full Git commit pin, selected annual JSON members without duplicates, and a new immutable output path. No silent overwrite of a frozen plan. It writes the JSON outside public GitHub; the code never uploads data. Runtime and original ZIP coverage must be verified before any actual engine run.

**Scientific caveats:** historical years have already been heavily examined. Neither the plan preview nor candidate-screen metrics are fresh independent OOS. Multiple comparison bias grows with the search universe; eligibility based on positive training months is not a significance test. Every real candidate must have stop-first/gap rules and the exact $0.40/oz all-in roundtrip fee reconciled. No monthly profit or live-trading guarantee.

## Verification performed locally this session

- 20/20 M1 signal invariants; 5/5 M1 CLI validation/dispatch; 2/2 independent random oracle parity tests; 1/1 full real-loader synthetic BID/ASK M1 reference/fast trade, month, week and equity report parity.
- 7/7 M15/H1 CLI tests; 2/2 full real-loader synthetic BID/ASK M15/H1 reference/fast report parity.
- 20/20 factory preview/fingerprint/year/window/ZIP preflight/immutability tests.
- Total of these session-local *new* tests: 57 passed against an extracted older core snapshot plus these exact new modules and locally mirrored CLI changes.
- 50,000 synthetic M1 candles: exactly 2,285 identical signals from independent old loop and optimized vectorized detection. Elapsed times for that local sample 1.4558s vs 0.0247s (~59x). Not a production benchmark.
- The extracted older core whole-suite attempt reached 130 pass and was stopped by missing pyarrow on a Parquet test, rather than a 100% full-repository completion. Local Python 3.13 differs from constrained CI Python 3.12.
- IMPORTANT: Current GitHub HEAD complete pytest, new frozen batch contract tests and CI success are NOT VERIFIED in this local session. No original private Gold ZIP was available to rerun original 13-field parity or any genuine historical backtest.

Next release gates: full pinned Python 3.12 pytest/CI on exact HEAD; original SHA-verified source replay and 13-field ledger parity; high-volume frozen jobs with strict accounting, multiplicity-aware selection and truly untouched preregistered forward validation; then UI and operational hardening. PR #1 stays Draft and unmerged. No raw ZIP upload, billing change, repo visibility change, or trading recommendation.
