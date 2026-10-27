# Generic liquidity-sweep contiguous lookback audit — 2026-10-27

## Finding and fix

`src/norisk_quant/liquidity_sweep.py` previously required only the immediately preceding completed M15/H1 bar to be contiguous with the candidate sweep bar. Its rolling N-bar channel could silently bridge an earlier missing complete higher-timeframe candle inside the N-bar reference window, causing a stale high/low to qualify as a fresh liquidity sweep.

The signal now requires **all N prior completed higher-timeframe bars plus the candidate bar to be consecutive**, by checking `bars.index[i] - bars.index[i - N] == N * period`. The resampled bars are sorted, unique, and anchored to their complete M1 intervals, so this check excludes an internal missing M15/H1 bar. A gap *before* the lookback window remains allowed.

## Reproduction and regression

Synthetic 16 consecutive M15 candles (15 source M1 observations each), with a bullish sweep in the final candle: one expected signal. Delete every M1 observation from candle 7 while leaving the immediately preceding candle intact: the old one-bar check still passed, but the N=12 lookback was interrupted; the corrected logic returns no signal. Delete candle 0, entirely before the actual 12-bar window: the signal remains.

Regression: `tests/test_liquidity_sweep.py::test_missing_bar_inside_prior_channel_invalidates_sweep`.

One **isolated local reconstruction** of the source algorithm and this regression passed (1/1) using Pandas 2.2.3 and pytest 9.0.2. This is **not** a complete installed-package or current-HEAD pytest pass, not an official GitHub Actions run, and not a replay on the private original Gold ZIP. Full repository CI and original-source checks must be evaluated independently.

## Scientific boundary

This is a data-integrity/causality correction to the generic `liquidity_sweep_signals` strategy, not evidence of profitability. Any prior numerical result obtained from this *generic* implementation before this fix is not directly comparable without rerunning and versioning. The separate frozen FAC013 43,200-run batch uses its own preregistered implementation; this change does **not** replay or amend its reported results, and must not be portrayed as a new FAC013 acceptance.

No strategy parameter, fee, private market data, CI billing, repository visibility, or PR merge state was changed. Keep PR #1 Draft and avoid live trading claims.
