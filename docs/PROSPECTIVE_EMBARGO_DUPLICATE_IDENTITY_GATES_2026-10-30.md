# Prospective validation: strict date, training embargo and duplicate-identity gates — 2026-10-30

This is a **code and synthetic-regression** change, not a market-data backtest or OOS result.

`scripts/freeze_prospective_validation.py` now enforces:
- Canonical ISO calendar dates `YYYY-MM-DD`; ISO week and compact date aliases fail closed.
- Frozen training years must be unique, ascending, actual integer years. This prevents misleading train/test chronology and boolean coercion.
- A mandatory, configurable **30-calendar-day default embargo** after the **last possible day of the last training year** before prospective evaluation begins. `--embargo-days` accepts only integers 1–366; the frozen file records the chosen value and last training date. This is a *temporal* leakage safeguard, not proof of independent data provenance.
- Repeated formula identities cannot occupy multiple prospective selection slots even when duplicated in otherwise plausible source records.
- Existing source SHA256, evidence sidecar, publish-once semantics, $0.40/oz fee, no-refit, training-only, no-OOS and no-live gates remain in place.

Use `python -m pytest -q tests/test_prospective_embargo_gate.py tests/test_freeze_prospective_validation.py` for focused synthetic tests. Full repository CI and actual private original-ZIP replays require independent verification on the exact commit.

**Limits:** The date gap is measured from December 31 of the last frozen training year, since the available training evidence is year-scoped. It does not prove the original data was never inspected, prevent adaptive multiple testing, replace forward pre-registration, or establish profitable months. Exposed 2012–2016 history is not clean OOS. This update executes **zero** new real-data backtests; monthly net P/L and floating M1 drawdown are **N/A**. Do not upload raw Gold ZIP, quote ledgers or private results. PR #1 must stay Draft.
