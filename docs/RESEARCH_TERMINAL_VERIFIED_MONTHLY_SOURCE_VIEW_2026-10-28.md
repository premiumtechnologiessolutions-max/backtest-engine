# Source-reverified private monthly Quant Terminal — 2026-10-28

## Scope and evidence boundary

`scripts/research_batch_verified_monthly_terminal.py` is a new **read-only offline HTML view** of **already executed** frozen batch jobs. It does **not** accept a standalone precomputed scorecard JSON as a source of truth. Instead, its CLI invokes the existing `research_batch_monthly_scorecard.scorecard` against the local private Gold ZIP, frozen plan, canonical result files, manifest and exact Git checkout. Optional **independently frozen** SHA256 evidence pins are passed through to the existing M1 floating-equity auditor. A mismatch aborts the export. Existing files remain untouched on a failed audit.

Run from the exact frozen clean repository checkout, with private archive and batch results available locally:

```sh
python -m scripts.research_batch_verified_monthly_terminal \
  --plan /private/frozen-plan.json \
  --batch-output /private/batch-output \
  --html /private/verified-months.html \
  --equity-pins /private/independently-frozen-equity-pins.json
```

The `--equity-pins` argument is optional. Without independently frozen pins, **all floating M1 drawdown and M1 gap fields are N/A**; the exporter never backfills them from inferred curves. Output uses the existing atomic, owner-only private HTML writer, not the public GitHub repo. Do not publish private HTML containing job metadata.

## What is displayed

- Every source-reconciled, exit-booked UTC monthly net P/L in USD/oz, monthly fills, all-in fees and observed M1 sample count.
- Per-job monthly positive count, worst month, net and **observed** M1 floating drawdown only when independently pinned.
- A filterable monthly ledger, English/Arabic toggle, responsive navy/gold presentation, keyboard focus indicators and explicit N/A.
- Clear **historically exposed standalone / not OOS / not shared capacity / not approved** status. There are no fabricated months, prospective returns, approved strategies, or live orders.

Renderer additionally checks aggregate monthly net, fills, fees, worst-month identity, observed counts, chronological order, finite values, pinned/unpinned risk coherence and job counts. Tests use **synthetic reports only**; they do not validate the original Gold ZIP or add real backtests.

## Limitations and release gates

This is a separate offline monthly-evidence page complementing the registry-only Quant Terminal, **not yet a unified interactive application or a worker**. No resumable job execution, independent prospective OOS, authenticated multiuser service, actual shared-capacity portfolio replay, deployment certification, or live trading. Original-source execution and the exact-head GitHub CI are required before treating any report as verified. The source-verifier cannot prove that pins were created independently at an earlier date; this must be evidenced externally. All 2012–2016 research remains historically exposed.

No billing/privacy changes, no private M1 BID/ASK upload, no MT5 live connection, and PR #1 remains Draft.
