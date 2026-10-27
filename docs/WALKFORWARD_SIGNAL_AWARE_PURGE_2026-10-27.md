# Walk-forward: signal-aware training purge (2026-10-27)

**Scope:** `src/norisk_quant/walkforward.py` `purge_cross_boundary_trades`.

## Failure mode

The previous selector retained trades whose **entry and exit** were inside the training interval, even if their `signal_at` occurred before `train_start_utc`. This could leak pre-training decision exposure into a training-only ledger, despite an otherwise valid entry/exit interval.

## Change

- Keep the existing entry/exit boundary purge.
- When a `signal_at` column exists, require explicit finite UTC-aware timestamps, reject a signal later than its entry, and **drop** trades whose signal predates the training start.
- Preserve compatibility with legacy trade tables containing only `entry_at` and `closed_at`.
- Reject invalid signal timestamps even on rows that would otherwise be excluded; do not silently cleanse corrupted input.

Regression tests: `tests/test_walkforward_full_trade_window.py`.

## Research limitations

This is a chronology/integrity guard, not evidence of profitability or independent out-of-sample performance. Historical years already examined during model selection are not fresh OOS. No raw Gold ZIP or price feed was uploaded. Full original-source 13-field replay parity remains blocked without the separately authorized original archive and independent reference ledger. Draft PR #1 must not be merged on the strength of synthetic tests alone.
