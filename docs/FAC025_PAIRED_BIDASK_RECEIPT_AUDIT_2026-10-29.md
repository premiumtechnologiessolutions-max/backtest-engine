# FAC025 — Paired BID/ASK M1 receipt audit (2026-10-29)

**Research-only integrity improvement; no original-source backtests, new P/L, floating M1 drawdown, clean OOS, or strategy approvals.** The frozen 72 correlated FAC025 settings remain one unexecuted hypothesis. Registry totals are unchanged.

## Why this is necessary

A completed BID candle is not enough to establish that the ASK candle and spread were available when the decision was made. The optional `scripts/research_fac025_bidask_receipt.py` adapter requires **both** synchronized quote-side OHLC and independently captured UTC `bid_received_at` / `ask_received_at` timestamps. Both complete bars must have arrived after their M1 close and **strictly before** the signal. It rejects missing fields, nonfinite or boolean prices, crossed synchronized BID/ASK open/high/low/close, impossible OHLC geometry and untrusted timestamp formats. The existing observed-M1 adapter still rejects missing/duplicate minutes and incomplete M15. Only BID context is forwarded to the frozen FAC025 gate; both receipts must be known.

It returns a descriptive minimum/median/maximum **observed M1 closing spread**, never an executable spread, fill model, or strategy profit. This paired audit assumes BID and ASK OHLC were aggregated from the **same tick coverage**; independently sampled feeds may legitimately fail the conservative synchronization gate and must not be silently resampled. Caller-supplied receipt timestamps are **not independently authenticated** and require trusted source evidence before any real-world causality claim.

## Verification and strict limits

`tests/test_research_fac025_bidask_receipt.py` exercises synthetic quote geometry, either-side late/impossible receipts, missing and duplicate M1, risk-halt propagation, and invalid types. Exact-head GitHub CI must succeed before reporting verified tests. No raw quotes are committed.

This module does not change frozen entry/exit, risk, session, or cost assumptions. No new historical or prospective strategy results, canonical parity, or shared-capacity portfolio have been produced. Acceptance still requires private SHA-pinned original Gold ZIP, exactly $0.40/oz roundtrip, next eligible open <=1 minute, stop-first and adverse gap-through, source-verified M1 drawdown and monthly after-fee P/L, one-slot shared-capacity replay, and embargoed prospective validation. Draft PR #1 remains unmerged; no MT5 live connection.
