# M1 executor quote-schema fail-closed gate — 2026-10-29

## Finding
All three executable research paths (`execution.run`, `fast_engine.run_fast`, and `limit_engine.run_limits`) accepted M1 OHLC columns through implicit `float(...)` / `to_numpy(dtype=float64)` coercion. Thus an already-built DataFrame containing numeric-looking **strings** or **booleans** could be silently interpreted as valid market prices. The ingestion layer has its own explicit normalization contract, but that does not protect direct callers, corrupted caches, or custom research entry points.

## Change
Introduced a shared `require_numeric_execution_ohlc` preflight and called it in **all three** executors before any replay loop. It rejects duplicate OHLC column labels, missing OHLC columns, and non-numeric or boolean column dtypes. Native integer and floating-point OHLC remain supported. Existing OHLC finite/geometry checks, time ordering, gap/stop-first rules, fixed all-in **$0.40/oz** fee and strategy definitions are unchanged.

## Synthetic controls
`tests/test_executor_ohlc_dtype_fail_closed.py` adds **43** synthetic test cases: 36 malformed quote cases (3 executors × 4 columns × 3 invalid dtype forms), 3 duplicate-column cases, 3 valid numeric zero-trade cases, and 1 valid reference/fast parity case with fixed fee. These tests have been committed but **must not be described as passed** without executing pytest on the current GitHub HEAD. No original Gold ZIP, broker ticks, or clean OOS were used.

## Acceptance limits
The source-normalization path may continue to explicitly parse numeric strings from raw CSV/JSON; execution never reinterprets already-constructed text or boolean quote columns. This dtype preflight is not a full independent source integrity check. It does not certify tick-level fills, end-of-data prices, original-source 13-field parity, strategy profitability, or complete CI. Keep Draft PR #1 unmerged until full constrained-environment pytest and original-source replay are verified. Do not upload the private Gold ZIP or change repository visibility/billing without explicit instruction.
