# CLI execution truthfulness gate — 2026-10-26

## Defect and impact

Before this change, `norisk backtest --strategy bos-fib --execution fast`
and `--strategy fvg --execution fast` were accepted, although the actual
dispatch called `run_limits()` (the reference limit-order executor) in
both cases. The report's recorded `run_parameters.execution` could
therefore say `fast` when no fast limit engine was run. This is a
**provenance/report-label defect**, not a discovered P&L discrepancy.

Additionally, `--bos-h1-max-age-minutes` without
`--bos-require-h1-trend`, or H1/dual-pivot flags with non-BOS
strategies, could be accepted while silently ignored.

## Fail-closed behavior

Argument validation now rejects:
- `--execution fast` with `bos-fib` or `fvg`.
- BOS/H1 gate flags supplied with any non-BOS strategy.
- Negative H1 age limits.
- H1 age limits supplied without enabling the H1 trend gate.

These checks run **before loading private market data**. Default behavior
and canonical `$0.40/oz` round-trip ALL-IN fee are unchanged.
The `fast` option remains available for supported market-signal
strategies. This patch does **not** add a fast limit-order executor.

## Verification and remaining gates

Seven parameterized regression cases are in
`tests/test_cli_execution_truthfulness.py`. A separate local
reproduction of the validation predicates passed 7 invalid and 6 valid
synthetic cases. This **is not** a run of the repository's pytest suite.

Still required: execute full package tests with pinned dependencies;
verify actual central 13-field replay against the original private
Gold data ZIP; and obtain a successful CI run once quota permits.
Do not treat historical training or already inspected years as fresh
out-of-sample. No raw market data or credentials were uploaded, and
Draft PR #1 must remain unmerged.
