# Frozen research JSON ambiguity gate — 2026-10-28

## Scope

Commit `39a84dd9c2cdfb5b552a052a910ff84b84c69ee8` adds
`read_strict_json` in `scripts/research_batch_orchestrator.py`.
Commit `6eac3d55da64c337c55b684490aeebce38d2e9ef` adds synthetic
regressions in `tests/test_frozen_batch_strict_json.py`.

The loader rejects duplicate object keys at **any nesting depth**,
nonstandard `NaN`, `Infinity` and `-Infinity` tokens, malformed
JSON, missing files and direct symlink paths. It is used for:

- the CLI's input frozen research plan;
- each backtest's `summary.json` before accounting reconciliation;
- an existing `batch_manifest.json` before resuming research.

This closes a gap where Python's default `json.load` silently selects
the last duplicate key, making the frozen plan/evidence ambiguous.

## Verification boundary

- A standalone copy of the strict JSON loader passed **12/12** local
  synthetic parser tests on Python 3.13.5 (not the full repository).
- The repository test file defines **17** synthetic test cases covering
  parser behavior and three orchestration boundaries. Those new tests
  have **not** been run against the complete checked-out GitHub source.
- No GitHub Actions success is claimed on the current head. The latest
  commit has no associated PR-triggered workflow run at audit time.
- Original Gold ZIP SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`
  has **not** been replayed in this change. The historical 13-field
  independent comparison is not current-head acceptance.
- The repository currently reports **public** visibility. No raw market
  data, account secrets, or private quote/trade ledgers were committed.

## Release gate

Keep Draft PR #1 unmerged until full pinned-environment `pytest`,
packaged CLI smoke, current-head CI, and independent original-source
13-field replay pass. This is an integrity hardening change, **not**
new evidence of strategy profitability, broker execution, or OOS success.
