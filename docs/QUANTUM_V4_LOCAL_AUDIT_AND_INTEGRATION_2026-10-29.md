# No Risk FX Quantum Trading Engine V4 — Local integration and research audit (2026-10-29)

## Status (truthful release boundary)

**V4 implementation exists as a separately SHA256-manifested local release ZIP in the owner's private ChatGPT workspace.** It has NOT been merged in this public repository. This document does not assert that the three overlay files or V4 UI routes are present on the branch. Branch PR #1 remains a Draft.

V4 mathematical brain features: 6 causal price-derived features, 5 bounded arithmetic operations, deterministic hypothesis hashes, training-only guided mutation/crossover, source ZIP SHA256 checks, SQLite resumable yearly observations, local loopback UI, one synthetic open position and fixed all-in 0.40 USD/oz roundtrip research cost.

**New required release gate:** before freezing a training-selected formula for later review, independently replay all its selected training years with **both** existing reference and fast market execution engines. Require 15/15 exact chronological ledger field parity (numeric epsilon 1e-8), full minute-equity parity, fixed accounting checks and the original per-year quote fingerprint. SHA-256-bind each successful receipt to the exact recorded training metrics, source, engine code and formula. Reject stale or modified records. Partial year verification is never promoted to completed-candidate status. Review-year information is never an input to mutation or ranking.

## Results on the user's original private Gold ZIP (not uploaded)

Original source SHA256: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Engine clean Git revision used for independently tested local API pipeline: `e7d7c9a2ddc1054a440fc227d6de661818146698`. V4 research overlay algorithm SHA256: `f29fc3180342e118a5bd69bbea52031a698bddaf9c2a87cc36879857b0fba2bf`.

- 103/103 local focused Python unit/integration tests passing on Linux Python3.13; JavaScript syntax checked via Node. No claims of latest full GitHub HEAD CI passing or testing on Windows.
- Single 2012 seed formula: **1,611 trades**, 4/12 positive calendar months, **−542.98 USD per ounce** net; full fast/reference independent ledger and equity replay passed, therefore **execution verified, trading hypothesis rejected**.
- Full local HTTP flow: **7** frozen mathematical formula candidates across 2012 and 2013 (**14** annual backtests); selected top 2 training formulas underwent **4 independent year reference replays** (2 candidates × 2 training years), passed 15-field and full-equity parity.
- Shortlist frozen **after** audit, then **2014 descriptive review** was executed only on the frozen two candidates. Their 2012–2013 training net USD/oz: **−893.46** and **−1048.20** respectively. Their 2014 subsequent net USD/oz: **−624.43** (2/12 positive months) and **−576.51** (2/12 positive months), respectively. **No edge; all selected candidates rejected.**
- 2012, 2013 and 2014 are historically exposed from prior research, so this is **NOT an independent fresh OOS** experiment. Reference/fast agreement does not validate actual broker tick fills or tick spread/slippage.

## Next integration work required before declaring completion

1. Port the standalone overlay's `src/norisk_quant/math_discovery.py`, `scripts/research_brain.py`, `scripts/research_brain_audit.py`, local authenticated UI/API and targeted tests into GitHub together, preserving SHA/code provenance and stable execution source paths.
2. Run exact pinned Python3.12 CI including Parquet/cross-year execution suites and Windows app startup.
3. Run substantially larger preregistered bounded research campaigns without treating a search over exposed historical data as fresh independent OOS; add source-clean forward broker-tick and prospective validation.
4. Maintain the no-broker-access safety boundary and no profitability or monthly-win guarantees.

**Public repo warning:** Original quote ZIP, per-candidate raw data/SQLite, locally stored private campaign traces, and any access token must never be committed here.
