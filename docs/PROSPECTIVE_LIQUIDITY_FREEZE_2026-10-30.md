# Prospective liquidity research preregistration — 2026-10-30

**Research status: frozen hypothesis only; zero prospective observations, zero edge claims.**

The original 2010–2026 Gold archive has been extensively inspected. Historical
2012/2013/2017/2020/2024 results and any other previously explored years are
**not independent OOS**, regardless of how often a backtest is repeated.

## New experiment (no optimization against the future window)

- Strategy: existing causal M1 prior-range liquidity sweep + reclaim
  `src/norisk_quant/liquidity_sweep_m1.py`, Git blob
  `0a070ef748e17076236000847505e3f5ba841657`.
- Frozen hypothesis: lookback=20 observed contiguous M1 candles;
  min sweep excess=$0.15/oz; reclaim=$0.05/oz;
  stop buffer=$0.10/oz; target=1.5R; max stop=$20/oz.
  Reject candles sweeping both range edges. Signal confirmed only at M1
  close; next observed open is the earliest possible execution.
- Exact roundtrip research cost: **$0.40/oz**. No broker fill certification.
- Existing historical reference archive SHA256:
  `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
  The archive is NOT included in the repository.
- Known historical exposure conservatively through **2026-10-30**.
- Planned forward collection window **2026-11-02 through 2027-01-29**.
  These are dates, not evidence that quotes or fills have been collected.
- Machine-checkable immutable plan:
  `research/preregistrations/sweep_reclaim_m1_2026-11-02.json`.
  Its canonical payload SHA256 is
  `8375c0d0866017891b5ae14d071a984362a05f76ab5cc79b725cca66d2f23a6e`.
  Preserve the original Git commit that first introduced the plan; a
  locally supplied `registered_at_utc` alone is not proof of chronology.

## Evaluation guard

`norisk_quant.preregistration.freeze_plan` verifies strict schema,
immutable parameters, $0.40 fee and nonoverlapping training/exposed/holdout
dates. `verify_freeze` rejects any altered frozen payload.
`authorize_future_evaluation` requires the exact pinned strategy Git blob,
a trusted external commit timestamp **before** the first holdout date, and
an evaluation window wholly inside the frozen interval. The caller must
independently verify that Git commit timestamp; the Python module does not
fetch or authenticate it.

The guard does not automatically run an experiment, establish data source
authenticity, prove first observation of the sample, or certify an edge.
A future research run must separately document the source's provenance,
BID/ASK M1 fingerprint, missing-minute calendar, independent execution parity,
monthly/weekly realized ledgers, forced exits, fees, selection count, and
untouched data chronology. Do not retune this frozen hypothesis after seeing
future results and still call it the same preregistered experiment.

**Next release gates:** run full repository CI at the exact new commit,
complete original private ZIP 13-field replay (not run in this change), and
collect genuinely later data under independently verifiable source provenance.
PR #1 remains Draft. No live trades or raw market archive uploaded.
