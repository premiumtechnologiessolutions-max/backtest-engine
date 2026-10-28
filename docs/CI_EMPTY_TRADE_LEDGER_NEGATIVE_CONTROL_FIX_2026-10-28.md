# CI repair: empty synthetic ledger schema (2026-10-28)

Exact-head GitHub Actions run 40746527220 on commit `346d91e2f7be98cebde22274e4689a9e6b679507` failed **one** test: `test_frozen_runner_rejects_shifted_monthly_pnl_even_when_total_matches` (1 failed, 1,763 passed). The synthetic `run_limits` stub returned an empty DataFrame with only `net_pnl`, so the newly required 15-field in-memory ↔ persisted trade-ledger integrity gate correctly rejected its malformed execution ledger *before* the intended independent UTC monthly allocation negative control could run.

This change repairs **only the synthetic fixture** to provide an empty execution ledger with all 15 audit fields, so the test can reach its intended monthly redistribution rejection. A new negative test explicitly requires the integrity validator to keep rejecting malformed empty execution ledgers. The production validator and trading/execution logic are unchanged; never weaken a fail-closed gate merely to satisfy an old test.

No new original-source M1 backtests, monthly P/L, equity drawdown, strategy acceptance or clean prospective OOS were produced. Existing registry counts and fixed $0.40/oz fee are unchanged. Keep PR #1 Draft, raw Gold ZIP private, and live trading disabled. Verify exact-new-head CI separately before claiming green status.
