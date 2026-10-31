# Read-only source-checked monthly scorecard — 2026-10-28

The new scripts/research_batch_monthly_scorecard.py audits **completed** frozen historical batch artifacts. Run on the exact clean frozen checkout with the original private archive:

    python scripts/research_batch_monthly_scorecard.py --plan /private/frozen-plan.json --out /private/batch-output

It verifies private source SHA256 and Git HEAD, reads a strict frozen manifest, re-runs canonical audit_run on each completed result, and emits monthly net P/L, trades, fees, observed M1 samples, worst month, positive-month count and zero-trade months. Missing results are explicitly NOT EXECUTED. No files are written, and the audit is capped at 500 jobs.

**Limits:** Floating M1 drawdown is N/A without source-attested monthly M1 equity evidence. Historical exposed standalone results are not independent OOS or a shared-capacity portfolio. No new Gold replay, new parameter grid, or strategy approval. The $0.40/oz model remains unchanged. No raw market data is uploaded. Exact-head CI and independent reference parity must be separately verified; keep PR Draft.
