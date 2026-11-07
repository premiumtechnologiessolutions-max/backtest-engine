# Original-source replay acceptance gate — 2026-11-03

Status: **BLOCKED ON PRIVATE ORIGINAL SOURCE; NOT CERTIFIED**.

This is an execution checklist, not a claim of successful backtesting or a new out-of-sample result. The October 25 local scoped tests and older source replays do not certify the current branch HEAD.

## Required immutable inputs

- Original private `Gold data.zip`, retained outside GitHub, SHA256 exactly `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
- Record exact Git commit SHA and pinned Python/dependency lock before starting.
- Use the actual repository runner `scripts/run_bos_fib_frozen_sensitivity.py`; do not substitute a copied standalone implementation.
- Run the four years **separately**, or as a batch only if the complete batch finishes successfully. An interrupted batch is not a pass.

## Required acceptance checks

1. Validate full 12-month UTC coverage per selected year; report missing minute/session anomalies separately. Monthly presence alone is not continuous coverage.
2. Reproduce the archived reference 13-field execution ledger on its original 2012 replay scope; compare trade counts, ordered records, timestamp, direction, entry/exit prices, exit reason and all remaining reference fields, with an explicit mismatch report.
3. Independently validate source BID/ASK fingerprint, exit-bar/exit-price consistency, source gaps, persisted trade equality, weekly/monthly bucket reconciliation, equity/accounting and exactly **$0.40/oz** all-in fees.
4. Preserve frozen strategy settings, including H1 max age 120 minutes and ignored dual pivots; record separate model provenance for the 689-trade historical base comparison and the 668-trade frozen 2012 variant. These are **different scopes** and must not be compared as identical ledgers.
5. Record source SHA both before and after execution, evidence manifest, complete logs, exact command, start/end timestamps, commit SHA, dependency versions and exit status. Reject missing evidence.
6. Mark every previously inspected year as **historically exposed**, never clean OOS. Do not authorize live trading from these tests.

## Research interpretation

Frozen BOS/H1 sensitivity (2012, 2017, 2020, 2024) remains **rejected**: 2,876 trades, 0/48 profitable months, -$1,226.22560 USD per one-ounce basis. These are separate annual runs, not a continuous portfolio. The distinct 2012–2016 quote-reopen gap reversal also remains rejected: 32 trades, -$1.34 net.

## Release blockers

- Exact-current-HEAD original-source replay with a complete independent comparison artifact.
- Pinned-environment full pytest and relevant CI at that exact commit.
- Truly preregistered, previously untouched forward evaluation of a distinct liquidity hypothesis.
- Durable-host crash/restart/resume test with truthful health status.
- Confirm repository visibility before uploading anything confidential: GitHub has reported this repository as **PUBLIC**. Never commit raw source archives or private ledgers.

**No profitability guarantee, broker tick parity, or independent OOS certification is implied.**
