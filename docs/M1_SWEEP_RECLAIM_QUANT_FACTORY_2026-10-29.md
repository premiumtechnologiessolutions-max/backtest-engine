# No Risk FX — Causal M1 Liquidity Sweep / Reclaim Research (2026-10-29)

## Implemented, not validated

Code: src/norisk_quant/liquidity_sweep_m1.py. CLI: norisk backtest --strategy m1-sweep --timeframe M1. Offline factory registry: scripts/research_batch_orchestrator.py. Synthetic tests: test_liquidity_sweep_m1.py, test_m1_sweep_cli_contract.py, test_m1_sweep_batch_contract.py, test_m1_sweep_vectorized_oracle.py.

### Frozen causal rules

- Compare only the current CLOSED M1 candle against the preceding N=20 observed and strictly continuous UTC M1 candles. Current candle is excluded from the rolling range. If any minute is missing, reject that candidate.
- Long: low strictly below previous N lows by > $0.15/oz and close strictly back above previous low by > $0.05/oz while inside the prior range. Short: symmetric sweep of previous high and reclaim back inside.
- Reject dual high+low sweeps: OHLC cannot identify their intrabar ordering.
- Confirm signal at candle CLOSE; earliest eligible entry is the next M1 open subject to existing market-engine expiry and conservative execution semantics.
- Stop distance is the wick-to-CONFIRMATION-CLOSE distance plus a $0.10 buffer (not an absolute stop at the wick). Target distance is stop × 1.5. Stops are placed relative to the entry open; overnight price gaps can change absolute levels.
- Reject stop distances > $20/oz. All quantities are explicit USD per ounce. Canonical fee remains exactly $0.40 per ounce all-in roundtrip; avoid double-counting spread or commission.
- Fast and reference execution are supported; neither constitutes observed broker tick execution.

CLI arguments: --sweep-lookback, --sweep-min-excess-usd, --sweep-reclaim-usd, --sweep-stop-buffer-usd, --sweep-reward-risk, --sweep-max-stop-usd. Restrict --timeframe M1.

Offline frozen factory example: a grid with strategy "m1-sweep", timeframe "M1", execution "reference", start/end period, id_prefix "m1sweep", and parameter arrays such as sweep_lookback [10,20,40], sweep_min_excess_usd [0.15,0.3], sweep_reclaim_usd [0.05,0.1], sweep_reward_risk [1.0,1.5,2.0]. The enclosing frozen plan requires source ZIP SHA, full pinned Git revision, absolute private dataset path, historical_exposed context, and jobs/grids. A plan is NOT an executed backtest.

### Local verification

- 20 synthetic M1 signal/invariant tests passed on extracted 2026-10-26 core.
- 5 local CLI tests passed for reference/fast dispatch, timeframe/fee controls, and $0.40/oz real execution (loading/report provenance mocked only).
- 2 additional independently computed randomized oracle tests passed, including four lookbacks with missing M1 quote minutes and append-future invariance.
- Synthetic 50,000-row microbenchmark: old candle loop and vectorized search produced exactly 2,285 identical signals; 1.4558s vs 0.0247s (approximately 59x in this particular local environment, NOT a general performance guarantee).
- Older extracted local suite: 130 passing then stopped on unrelated missing pyarrow dependency for Parquet testing (Python 3.13 environment, target pinned Python 3.12). This is NOT a verified full-suite run of latest GitHub HEAD.
- Frozen research-batch contract tests, current HEAD full pytest and GitHub Actions on this HEAD are NOT confirmed green.

### Limitations / next gates

No original Gold data.zip archive has been found accessible during this session. Original SHA-pinned 13-field replay, canonical multi-year runner, true independent preregistered OOS testing and tick-level broker validation remain pending. Historical BOS/H1 research is negative and rejected. No profitable-month guarantee, no live advice. Do not upload raw quotes; keep PR #1 Draft/unmerged; do not alter spending or repository visibility.
