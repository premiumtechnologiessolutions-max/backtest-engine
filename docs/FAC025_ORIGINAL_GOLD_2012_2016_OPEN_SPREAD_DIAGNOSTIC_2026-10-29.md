# FAC025 — original Gold ZIP paired-open spread diagnostic (2026-10-29)

**Local source SHA256 VERIFIED:** `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` (155,808,257-byte private `Gold data.zip`). The original ZIP was materialized from the user's private ChatGPT Library and inspected **locally only**. No raw M1 BID/ASK, member JSON, quote timestamps, or credentials were committed to this public GitHub repository.

This is a **source-quote data-quality and fixed-cost sensitivity diagnostic, NOT a backtest**. For each of the 2012–2016 annual JSON members, read all observed rows with UTC epoch-second `ts`, BID `o,h,l,c`, ASK `ao,ah,al,ac`. Check BID and ASK OHLC consistency, crossed corresponding OHLC extrema, and count a gap event whenever consecutive observed timestamps differ by >60 seconds. Compute observed *open* spread as `ao - o` per existing minute, sort within each year, report median, nearest-rank-style index `floor(0.95*(n-1))`, maximum, and count of opens with spread strictly >$0.40/oz. No synthetic minutes, no imputed receipts, no position fills, no change to fees.

| Exposed year | Observed M1 | Median open spread $/oz | P95 open spread $/oz | Max open spread $/oz | Opens >$0.40 | % opens >$0.40 | Gaps >1m | Crossed OHLC | Invalid OHLC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2012 | 352,975 | 0.36 | 0.54 | 2.95 | 82,104 | 23.261% | 708 | 0 | 0 |
| 2013 | 352,317 | 0.35 | 0.57 | 2.98 | 77,291 | 21.938% | 893 | 0 | 0 |
| 2014 | 351,794 | 0.28 | 0.38 | 2.97 | 14,579 | 4.144% | 533 | 0 | 0 |
| 2015 | 353,772 | 0.30 | 0.40 | 2.34 | 18,788 | 5.311% | 300 | 0 | 0 |
| 2016 | 354,246 | 0.30 | 0.40 | 2.84 | 18,759 | 5.295% | 289 | 0 | 0 |
| **Total** | **1,765,104** | — | — | — | **211,521** | **11.983%** | **2,723** | **0** | **0** |

A pronounced **2013-07** source regime is visible: 24,599 / 31,280 observed minute opens (**78.64%**) have ASK-BID open spread >$0.40/oz. This is **not** a count of trade entries or losing trades. Gaps may include normal weekends/holidays; their causes were not independently classified. No synchronized tick-coverage or broker execution provenance was established.

**Critical economic distinction:** The frozen model's **exactly $0.40/oz ALL-IN roundtrip** remains unchanged. It is **not** valid to add the observed spread on top of this fixed all-in fee and call the result the same model. The observed quote-side discrepancy is instead a warning that the BID-only proxy may be optimistic for BUY entries and a reason to run *separately labeled* spread-aware stress tests. The source ZIP has no independently verified `bid_received_at`/`ask_received_at` fields, so the newly implemented FAC025 paired-receipt entry audit cannot be promoted to authenticated causal execution by inventing those timestamps.

**Evidence limits:** 0 new strategy backtests, new monthly P/L N/A, worst strategy month N/A, new floating M1 DD N/A, 0 approved strategies, no independent prospective OOS, no broker/tick fills. 2012–2016 remain exposed historical years. The shared one-slot portfolio and source-authenticated paired execution remain outstanding. Keep PR #1 Draft/unmerged; no live MT5.
