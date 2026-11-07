# Source-pinned month-local M1 floating-equity drawdown — 2026-10-30

**Scope:** additive engineering integrity check, synthetic tests only. No new original-source strategy replay, monthly net profit, shared-capacity portfolio or prospective validation.

The existing `scripts/research_equity_m1_audit.py` independently checks SHA256 pins for `summary.json`, `monthly.csv` and `equity_m1.csv`, exact source archive and engine commit, chronological observed UTC M1 timestamps, equity arithmetic, global peak drawdown, monthly counts and month-end equity.

This change additionally calculates `month_local_max_observed_m1_close_drawdown_usd_per_oz` **from the same verified observed M1 marks**. The first UTC month starts with a zero-equity anchor. Each subsequent UTC month starts at the **last observed equity mark from the previous observed month**, resets its own peak, and uses only actual subsequent marks. It does not interpolate missing minutes or infer intrabar extremes. The existing `max_observed_m1_global_peak_drawdown_usd_per_oz` remains separate: a global high-water mark can predate the month and make that month's global-peak drawdown larger than its own month-local peak-to-trough.

The canonical batch scorecard exposes the monthly local drawdown and maximum across months **only when independent evidence hashes are supplied and re-audited**. Missing hashes produce JSON `null` (UI: N/A), not invented risk. Three new synthetic source-audit tests cover global-versus-local separation, a local intramonth peak, and an observed gap crossing a month boundary. Existing pinned scorecard tests also assert new fields and absent-evidence behavior.

Fixed fee remains **exactly $0.40/oz ALL-IN roundtrip**, already reflected in canonical equity. Do not charge it again. This is **not** a historical original Gold ZIP replay, strategy approval, actual shared-capacity portfolio, or OOS certification. Original-source monthly profit and drawdown remain **N/A** until independently replayed on SHA-authenticated private BID/ASK data. Keep Draft PR #1 unmerged and never publish raw Gold ZIP.
