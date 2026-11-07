# Shared-capacity portfolio M1 OHLC dtype gate — 2026-10-29

## Audited failure mode

The single-strategy reference, fast, and limit executors already call
`require_numeric_execution_ohlc` before converting M1 quotes to floats.
However, the three shared-capacity executors (`run_portfolio`,
`run_limit_portfolio`, `run_unified_portfolio`) were still using
`to_numpy(dtype=float)` directly. This could silently reinterpret a
cached/manual numeric-looking text quote or boolean quote as an executable
price, despite the single-strategy engines rejecting the same input.

## Change and verification boundary

All three shared-capacity engines now use the existing shared, fail-closed
OHLC schema gate **before** their unchanged finite-value and geometry checks.
The gate rejects missing/duplicate OHLC columns and nonnumeric/boolean
column dtypes. The source ingestion layer may still parse raw JSON/CSV
as explicitly documented. No execution order, stop-first convention,
strategy parameters, market data, fee or report arithmetic was changed.

`tests/test_shared_portfolio_ohlc_dtype_fail_closed.py` adds 42
synthetic regression cases: 36 coercible invalid quote cases, three
duplicate-column cases and three valid-numeric controls. Passing tests
must be confirmed on the **exact commit** in GitHub Actions; merely
committing these tests is not verification.

## Scientific and security limitations

This is software input-integrity hardening, **not** original Gold ZIP replay,
13-field historical parity, clean out-of-sample evidence, broker tick
execution, or profitable strategy certification. The canonical all-in
research fee remains $0.40 per ounce per roundtrip. Do not upload raw
private market data. Draft PR #1 stays unmerged.
