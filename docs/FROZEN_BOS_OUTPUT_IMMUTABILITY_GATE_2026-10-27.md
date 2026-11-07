# Frozen BOS annual runner: preserve prior report evidence (2026-10-27)

## Issue and correction

Before this change, `scripts/run_bos_fib_frozen_sensitivity.py` called
`destination.mkdir(..., exist_ok=True)` and the downstream `report()` writer
wrote `summary.json`, `trades.csv`, `monthly.csv`, `weekly.csv` and
`equity_m1.csv` to predictable paths. Re-running with the same output directory
could overwrite earlier audited results and provenance without an explicit
refusal. That risks destroying a reproducibility record even if the market
source and strategy settings have not changed.

The runner now checks its output path **before hashing the private source,
loading any market data, or running the strategy**. A missing directory or
existing empty directory is allowed; an existing nonempty directory, regular
file, or symlink is rejected with `FileExistsError`. Prior results are left
unchanged. This change does **not** alter signals, execution, fees, or the
canonical original-source SHA contract.

## Verification boundary

Five isolated local helper checks passed (missing/empty destination,
nonempty destination with file, nonempty destination with directory,
regular-file destination, symlink destination). Four repository regression
tests were added, including an `execute()`-level test that asserts a
sentinel historical trade ledger remains byte-for-byte unchanged after a
rejected rerun. **The full current GitHub repository pytest suite and
current-HEAD GitHub Actions CI have not been verified by this change.**
These checks are about output immutability, **not** original Gold ZIP
13-field parity or a new market-data backtest.

Remaining limitations: the writer is not a fully transactional multi-year
export; interruption after the first year may leave partial output in the
new directory. A subsequent attempt must use a fresh directory rather than
silently resuming/overwriting. The source ZIP must remain outside GitHub.

## Research status

The exposed 2012/2013 factory remains exploratory and is **not clean OOS**.
FAC021 is rejected (0/2,304 frozen joint passes; best 17/24 positive months).
No strategy is approved for live trading, and the fee remains exactly
USD 0.40 per ounce per roundtrip.
