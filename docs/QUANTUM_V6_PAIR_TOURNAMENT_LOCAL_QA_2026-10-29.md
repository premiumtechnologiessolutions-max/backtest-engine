# No Risk FX — Quantum Trading Engine V6 Pair Tournament (2026-10-29)

## Scope / accurate status

**Standalone V6 release produced locally, not yet a merge-ready repository implementation.** The original Gold ZIP remains private and is **not** uploaded to GitHub. The release is a loopback-only local UI + overlay on a clean Git engine checkout; the mathematical Brain/Pair overlay source has **not** been fully synchronized to this PR branch.

V6 introduces a TRAIN-only frozen strategy-pair tournament. It ranks complete formula candidates using TRAIN years only, freezes a selected universe before pair replays or later descriptive review, and tests each pair on **one actual shared synthetic OHLC execution ledger** using `run_unified_portfolio` (max 1 open position, max 1 oz, $0.40/oz all-in fee). It DOES NOT sum independent strategy P/L curves, claim independent OOS, place broker trades, or certify positive edge.

- Persist each pair/year's accounting-validated metrics and provenance in SQLite, then resume missing pair/year jobs only.
- Reject altered frozen shortlist SHA256, duplicate IDs or changed source/code/algo, and refuse further hypothesis mutation in a frozen campaign.
- Suppress candidate rankings until all pair/year research observations in the frozen universe have completed.
- Local authenticated API endpoints: `POST /api/brain-pairs-start`, `GET /api/brain-pairs-report`, and `GET /api/brain-pair-monthly?pair_id=...`. The monthly endpoint reads only training P/L and checks fixed universe, source and code provenance.
- UI displays bounded budgets, stop/resume status, 1-oz capacity caveat, six-pair ranking and month-by-month realized training P/L, with explicit NOT OOS / NOT LIVE labels.

## Reproducible local Gold replay (QA only)

- Original private archive SHA256: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
- Clean **local** QA checkout: `e77b5843da0d6349d3cf531d859baab9b99e9d1e`. This is a local commit only, **NOT** asserted to exist in the public remote GitHub branch.
- Two completed historical training years: 2012 and 2013.
- Four candidate formulas trained in eight annual backtests; six pair variants researched across 12 actual annual shared-capacity replays. Jobs were successfully recovered after interrupted execution without redoing completed years.
- All six pairs were **REJECTED** in training. P/L USD/oz and positive months (of 24), sorted by the product's descriptive training score: 
  - `scaled_return + prior_channel_displacement`: **−816.41**, **8/24**;
  - `prior_channel_displacement + wick_imbalance`: **−781.94**, **7/24**;
  - `scaled_return + wick_imbalance`: **−912.87**, **7/24**;
  - `wick_imbalance + reversed_scaled_return`: **−1,466.37**, **4/24**;
  - `scaled_return + reversed_scaled_return`: **−1,392.25**, **3/24**;
  - `prior_channel_displacement + reversed_scaled_return`: **−1,440.00**, **1/24**.
- Two single-formula standalone outcomes from the 2012–2013 baseline test: 3,280 trades / −893.46 USD/oz; 3,273 trades / −1,551.64 USD/oz. Their same-capacity paired result had **3,254 actual trades** / −1,392.25 USD/oz (3/24 positive months), showing why standalone P/L must not be added.
- **124/124 targeted tests passed locally** on Python 3.13 with V6 mathematical overlays and source snapshot. An actual HTTP loopback request using the built V6 ZIP proved the expected pair report and 24 monthly cells, rejected a wrong session token, and retained NOT OOS status. JavaScript syntax check passed.
- Automated Chromium GUI navigation to `127.0.0.1` failed with `ERR_BLOCKED_BY_ADMINISTRATOR` due sandbox browser policy. Windows Python 3.12 and complete GitHub CI for the exact V6 overlay are **NOT verified**.

## Deliverables / release integrity

Local source distribution `NoRiskFX_Quantum_Trading_Engine_V6_2026-10-29.zip` SHA256 **`ae6f0a7e64fc3e2b88b0a158d6842e3db52cbbe9c80f2ae83489e8a162324a3c`**, with 26 manifest-pinned source/test/doc files plus manifest; no original raw Gold ZIP, quote CSV, trade-level Gold source bytes or private SQLite. It contains sanitized aggregate research reports only. Distribution stored as a ChatGPT conversation artifact, not committed to this PR.

**Release blockers remain:** integrate V6 source/tests into the repository on an immutable commit, run pinned GitHub CI/Windows installer/GUI, original quote-feed parity and tick-level broker validation, preregistered genuinely untouched future paper-trading, and multiplicity-aware robust edge confirmation. **No edge has yet been validated**. Keep PR Draft/unmerged, no visibility or billing changes.

> Note: Quantum Trading Engine is a quantitative research product name; it does not use actual quantum computing hardware.
