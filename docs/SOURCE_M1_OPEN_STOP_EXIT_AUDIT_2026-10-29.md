# Source M1 BID open-stop exit audit (2026-10-29)

## What this closes

The frozen annual BOS/H1 sensitivity runner and the independent archived 13-field replay previously checked accounting, exit-reason geometry, and (for end-of-data) the final observed source BID close. However, an `open_stop`, `gap_stop`, or `entry_open_beyond_stop` row could match the archived ledger and be financially consistent while reporting an opening-stop exit price different from the actual **observed M1 BID open**. Matching ledgers alone cannot independently validate this source-price relation.

The new `norisk_quant.source_exit_integrity.verify_source_open_exit_prices` checks every such row against the **actual loaded M1** used by the engine. It requires a matching UTC source minute, equality to that minute's BID open (absolute tolerance 1e-7), an adverse rather than favorable stop fill, and consistent exit-path timing:

- `gap_stop`: an already open position, exit after a source M1 gap exceeding one minute.
- `open_stop`: an already open position, exit on a contiguous next observed M1 minute.
- `entry_open_beyond_stop`: entry and exit at the same observed M1 minute.

It rejects missing, duplicated, unaligned, non-UTC or unsorted source timestamps; nonnumeric or invalid BID opens; and invalid trade exit fields. Other exit reasons remain under existing price/reason and ledger validators.

## Wiring and verification

Integrated directly after `run_limits` in both `scripts/run_bos_fib_frozen_sensitivity.py` and `scripts/verify_bos_h1_parity.py`, before any replay may be reported as reconciled. Both now record `source_open_stop_exits_verified` counts. `tests/test_source_exit_integrity.py` covers 14 synthetic cases, including matched open/gap exits, adverse short fill, incorrect source price, wrong gap classification, impossible same-minute entry, missing source timestamp, favorable stop fill, malformed source schema and boolean prices.

**Validation boundaries:** The 14 synthetic cases were exercised in an isolated local Python 3 environment, not against the original private Gold ZIP. The full GitHub CI status on this exact commit must be checked separately. This source check is NOT tick-by-tick fill authentication, does not establish actual BID/ASK execution, and does not prove that a source candle was available at signal time. It also does not establish independent OOS or profitable monthly performance.

The original archive SHA-256 remains `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`; the canonical all-in fee remains exactly **$0.40 per ounce**. Do not upload the original archive to this currently public repository. PR #1 remains Draft and unmerged until the private-source replay and acceptance gate pass on the current checkout.
