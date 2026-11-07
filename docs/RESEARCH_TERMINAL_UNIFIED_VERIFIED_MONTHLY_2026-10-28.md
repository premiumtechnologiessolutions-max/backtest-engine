# Unified Quant Terminal — source-reverified monthly evidence (2026-10-28)

The primary `scripts/research_terminal.py` now supports an **explicit opt-in** to the already existing source-verified monthly scorecard, instead of requiring the operator to open a separate standalone HTML page. Default operation remains metadata-only with monthly P/L and floating M1 drawdown **N/A**.

Example (all paths local; never commit private datasets or generated reports):

```bash
python scripts/research_terminal.py \
  --verified-monthly-plan /private/frozen_batch.json \
  --verified-monthly-output /private/canonical_batch \
  --out reports/research_terminal.html
```

Optionally supply `--verified-monthly-equity-pins /private/independently_frozen_pins.json` for independently SHA-pinned M1 floating equity evidence. All three option values are *paths*, not a precomputed scorecard. A plan/output pair is mandatory; standalone pins are rejected.

The CLI calls `research_batch_monthly_scorecard.scorecard` on the **private original source and exact frozen checkout**, and the new `research_terminal_verified_monthly_section` invokes the strict monthly report validator again before rendering. Failures abort the export; no fallback to unverifiable numbers. The navy/gold responsive Research Terminal gains a **Monthly Evidence** tab, source-reconciled UTC monthly net P/L, actual fills, fixed $0.40/oz fees, M1 sample counts, independently pinned floating drawdown and gap counts (otherwise **N/A**), worst month, nonpositive-month streak and worst three complete months. Job/month controls filter the embedded rows without network requests. Export is capped at 20 audited jobs and 2,400 monthly rows to avoid oversized local HTML. It uses the existing private atomic 0600 writer.

**Limits:** These are historical *standalone* results; there is **no** shared-capacity portfolio P/L, clean prospective OOS, broker-tick execution proof, live orders, approval or claim of profitable months. The underlying scorecard may require the full original private archive, which is not available in public CI. Synthetic tests only exercise the new integration and security gates; no new real XAUUSD backtest was executed by this change. Do not upload the original Gold ZIP, raw quotes, generated HTML or private run ledgers to the public repository. Keep PR #1 Draft until independent acceptance gates pass.
