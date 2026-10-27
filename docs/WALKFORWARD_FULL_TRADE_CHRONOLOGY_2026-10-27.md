# Walk-forward training-only full-trade chronology gate — 2026-10-27

## Defect and impact

Previously, `require_training_only(..., time_col="closed_at")` checked only
`closed_at`. A trade that **entered before the training window** could be
accepted for parameter selection if its exit was inside the window. Similarly,
an entry in the window could be accepted even if the original signal was
generated before the window. Exit-only checks are insufficient for research
splits because such trades consume information from before the declared
training start.

## Fix

When `time_col="closed_at"`, validate any available `entry_at` and
`signal_at` columns as explicitly UTC-aware, nonmissing timestamps.
Require **train_start <= signal <= entry <= close < train_end_exclusive**
for the columns that are present. The existing embargo/evaluation rejection
for the close remains in force. If only `closed_at` is supplied, preserve
the old supported use case for exit-booked aggregate summaries.

This is a **validation-only** change. No signal generation, fills, fees,
strategy parameter, dataset split, or trading outcome was modified.

## Regression coverage

`tests/test_walkforward_full_trade_window.py` checks pre-training entries,
pre-training signals, impossible chronology, naive/non-UTC/missing entry
timestamps, legitimate UTC trades, closed-at-only summaries, and embargo
entries. The suite is synthetic; it is not a replay of the original Gold ZIP.

## Outstanding release gates

Require exact-head GitHub Actions success; original-source 13-field historical
replay parity is still unverified on the current head. The original ZIP must
not be uploaded to this public repository or GitHub Actions. Research
historical years are exposed, not clean out-of-sample evidence. PR #1 stays
Draft and no live trading is authorized.
