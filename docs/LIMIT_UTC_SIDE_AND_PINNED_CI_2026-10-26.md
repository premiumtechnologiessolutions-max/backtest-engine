# Standalone Limit UTC / side contract and constrained CI — 2026-10-26

## Scope and evidence

This change was inspected against the actual private GitHub branch `feat/quant-engine-foundation`.
It is **not** an executed full-repository test run and is **not** a broker-tick fill
validation. The original `Gold data.zip` (SHA-256
`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`)
and independent 13-field reference ledger are not available in the current
execution environment. Do not infer replay parity from these code changes.

### Input contract

- `LimitOrder.side` must be an integral +1 or -1, not a boolean or a float
  that happens to compare equal to 1. This aligns the standalone Limit
  interface with the existing Market `Signal` contract.
- `run_limits` requires unique, sorted, nonmissing UTC minute-open timestamps,
  consistent with `execution.run` and `fast_engine.run_fast`.
- A limit placement with an explicit non-UTC offset remains valid, but
  `trades.signal_at` is converted to UTC for a canonical ledger.
- New regression cases are in `tests/test_limit_input_contract.py`; **not yet
  executed as part of the exact current GitHub commit**.

### CI reproducibility preparation

`constraints-ci.txt` records package versions from the previously audited
Python 3.12.14 Windows snapshot at
`docs/audits/local-package-verification-2026-10-25.json`.
The manual-only `.github/workflows/ci.yml` now selects Python 3.12,
installs under these version constraints, prints the environment,
runs `pip check`, compiles Python files and executes the full `pytest -q` suite.

These constraints pin package *versions*, not artifact SHA-256 hashes or the
OS/Python patch release. They do not guarantee byte-for-byte reproduction
across Windows/Linux or future package indexes. A Linux CI pass is still
required; the old 263/263 local tests were run against an earlier commit.

### Unchanged safeguards and blockers

- Canonical research round-trip fee remains **exactly USD 0.40/oz ALL-IN**.
- No raw historical market data uploaded, no strategy profitability retests,
  no live trading and no private repository publication.
- Actions remains manual-only until the previously documented quota/runner
  blocker is resolved; do not change spending or dispatch repeatedly.
- Draft PR #1 must remain unmerged pending full pytest on current HEAD,
  original-source SHA verification, independent 13-field replay parity, and
  a successful CI run.
