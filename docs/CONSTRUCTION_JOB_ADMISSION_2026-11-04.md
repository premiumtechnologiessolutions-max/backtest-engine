# Construction-only inert job admission (2026-11-04)

`scripts/construction_job_admission.py` implements a pure, deny-by-default schema check for future research-job control-plane integration. It accepts only three inert kinds: `static_audit`, `synthetic_unit_test`, and `synthetic_contract_test`. Every request must name a pinned 40-hex source commit and a path under `tests/fixtures/synthetic/` ending in `.json`. It rejects unknown fields, commands, arbitrary paths, real-data requests, and unrecognized job kinds.

**Important limitation:** `admit` returns a normalized descriptor only. It does not authorize shell execution, verify fixture contents or existence, start workers, access markets, or constitute an execution sandbox. Callers must enforce isolated execution, fixture provenance, quotas, and access controls separately. Do not wire this module to an unattended executor without a separate explicit approval and security review.

Focused local test: `python -m pytest -q tests/test_construction_job_admission.py` — 17 synthetic tests passed in a standalone copy before commit. Full repository CI on the resulting head must be verified independently. No Gold ZIP, live trading, LEAN, NautilusTrader, OpenBB fetch, autonomous agents, backtest, or market-data replay was run. No monthly P/L or drawdown result was produced. PR #1 stays Draft and the historical registry is unchanged.
