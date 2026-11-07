# No Risk FX Quant Lab V3 — Research Brain release status (2026-10-29)

## Delivered as a standalone release overlay (NOT yet merged into this repo)

The conversation distribution `NoRiskFX_QuantLab_Research_Brain_V3_2026-10-29.zip` contains the actual additional source modules:
- `src/norisk_quant/math_discovery.py`: a deterministic, causal, finite arithmetic grammar of six price-derived features, five operators, configurable time windows, long/short thresholds, risk distance and cooldown. No Python eval, network calls or broker access.
- `scripts/research_brain.py`: bounded evolutionary research loop with training-only genetic mutation/crossover, training-failure-guided changes, SQLite WAL/year checkpoints, lock and source/code SHA256 provenance, completion budgets and stop-after-current-year behavior.
- `scripts/quantlab_desktop.py` and `scripts/quantlab_desktop_ui.html`: localhost-only authenticated Research Brain controls, progress, results and a write-once separate later-year review.
- V3 launcher mounts only the mathematical overlay outside the clean official Git checkout, pinning the new overlay bytes independently. **Do not copy modules into the Git repository without a tested matching commit and full CI.**

## Local verification performed

- V3 targeted `pytest`: **78/78 passed** in Linux/Python 3.13. Actual Windows/Python 3.12 test **not performed**.
- The exact packaged release (not just development sources) passed its 17-file release manifest SHA256 check and ZIP CRC.
- A real localhost API end-to-end test loaded the authorized original Gold ZIP SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`, clean local Git baseline, separately pinned overlay source, then completed a full 2012 train-year formula: 1,611 trades, 4/12 positive months, **-542.98 USD/oz net**, $0.40/oz fee. This is a *negative* training result.
- Eight 2012 mathematical candidates were executed in local preview; one was a training-feedback mutation. All rejected. A longer 2012–2013 preview saved 19 completed annual runs with 9 fully evaluated formulas and one incomplete formula before runtime budget/timeout; historical preview used an explicitly unpinned prototype build, NOT the GitHub CI revision.
- Review years are separated, frozen before inspection, and must not modify training candidate rankings.
- No new strategy has a certified independently prospective edge; no claims of profitable every month; no trading orders.

## Still required before final product / live approval

1. Integrate exact V3 source into branch and obtain HEAD-specific CI/Windows verification; do not overwrite concurrent research branch updates.
2. Rerun selected candidates via full canonical independent reference/fast trade-level audit (the evolutionary stage currently has strict *fast engine accounting*, not full broker source-bar replay).
3. Run large bounded research batches and compare complete same-identity multi-year results.
4. Preregister a fresh prospective untouched validation set and provider BID/ASK tick-execution model; account for multiple testing, gap and slippage risks.
5. No raw Gold ZIP uploaded to GitHub or published in the distribution. Keep Draft PR #1 unmerged until the above gates are passed.

No GitHub billing, visibility or branch-merge actions were authorized or taken by this V3 overlay release.
