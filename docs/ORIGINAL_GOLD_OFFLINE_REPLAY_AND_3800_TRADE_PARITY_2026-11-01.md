# Original Gold research replay audit — 2026-11-01

## Outcome (real original archive, offline, no raw data uploaded)

This verification **executed** the existing engine and audit scripts against the
previously uploaded user's *original* `Gold data(1).zip`, available locally via
the user's private file library. Archive SHA256:

`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`

**Validation 1 — frozen four-year BOS/H1 sensitivity**

Command: `python -m scripts.run_bos_fib_frozen_sensitivity --gold-zip PRIVATE_ORIGINAL.zip --years 2012 2017 2020 2024 --out PRIVATE_DIRECTORY`.

- Runner completed with **exit status 0**; the independent frozen
  `evidence_manifest.json` checker verified **25 inventoried evidence
  files**, plus its manifest.
- All **26 of 26 output files were SHA256 byte-for-byte identical**
  to the separately retained private
  `NoRiskFX_Official_Frozen_4Year_Evidence_2026-10-29.zip`.
- Yearly original M1 observations and ledger results:

| Year | M1 observations | Executed trades | Positive months / 12 | Net USD per 1 oz |
| --- | ---: | ---: | ---: | ---: |
| 2012 | 352,975 | 668 | 0 | -242.85294 |
| 2017 | 352,785 | 282 | 0 | -129.69146 |
| 2020 | 355,432 | 929 | 0 | -387.98588 |
| 2024 | 355,893 | 997 | 0 | -465.69532 |
| **Total across four independent years** | **1,417,085** | **2,876** | **0 / 48** | **-1,226.22560** |

These are **separate one-ounce year experiments**, not one continuous
portfolio or a demonstration of profitability. Execution used the frozen
**$0.40 per ounce ALL-IN** completed-trade fee and conservative M1 fill
rules, not actual broker ticks.

**Validation 2 — independent archived 13-field BOS/H1 trade matching**

Command: `python -m scripts.verify_bos_h1_parity --gold-zip PRIVATE_ORIGINAL.zip --reference-root PRIVATE_REFERENCE --years 2012 2013 2014 2015 2016 2017 2018 2019 --out PRIVATE_PARITY_JSON`.

- Runner completed with **exit status 0**, status **PASSED**.
- **16 distinct year/variant scenarios** (H1 only; H1 plus frozen 5x
  gross reward-to-fee filter) across 2012–2019.
- **3,800 executed trades matched all 13 prescribed execution fields**
  against the privately retained *independent* historical reference
  ledger, with the verifier's chronology, accounting, exit-price,
  source-open and source-bar checks applied.
- This **legacy 3,800-trade comparison is a different fixed strategy
  configuration** from the 2,876-trade four-year conservative sensitivity;
  do not combine them into a single portfolio or double-count trials.

## Code provenance and current branch correspondence

The code was run locally from the GitHub Actions verified-code archive
produced by [Engine quality gates run 41290384851](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41290384851),
not by executing GitHub Actions with raw market data.

At the check against PR #1 branch HEAD `deab3cc2a53152f2519a3db26ca4eded13a36330`,
the **exact Git blob identities of these five replay-critical modules**
matched the local executed snapshot:

- `scripts/run_bos_fib_frozen_sensitivity.py`: `8542ab801984dfdd37f102b4c33c3aea1859e4e3`
- `src/norisk_quant/bos_fib.py`: `62be293799d6d467bcd357ca45649fb83db73333`
- `src/norisk_quant/h1_regime.py`: `7637eb97c0f44834edc9414537ffe1a047d2cb8e`
- `src/norisk_quant/limit_engine.py`: `5cd636bc7fe5000e92e927b3d7f2546ce5a625b7`
- `src/norisk_quant/data.py`: `bf66bda033191ce194612ec7bb6aa0d6077cd0be`

**CI on exact HEAD `deab3cc2` passed 3,337 pytest tests**, as observed in
[run 41290985103](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41290985103).
CI is synthetic and **does not access the Gold ZIP**. Do not confuse
the successful offline source replay with a full fresh private-data
acceptance run on every byte of the latest Git HEAD.

## Remaining release blockers — do not mark complete

1. No genuinely untouched independent prospective/forward OOS results
   or correction for past strategy selection have established an edge.
2. No real broker tick-order/fill, commissions beyond the canonical
   all-in assumption, or live trading certification.
3. A source-pinned, end-to-end *full platform* acceptance on the final
   immutable build, including automated campaign generation, immutable
   lineage, resume, UI and full-repo integration, remains a separate gate.
4. No guarantee or evidence of profitable **every-month** operation.

Private archive bytes, original tick/quote history and trade/equity
ledgers were **not committed to GitHub**. Public-repo visibility was
left unchanged; PR #1 remains Draft/unmerged. Do not promote this
historically exposed strategy to live trading.
