# No Risk FX Quant — full historical training pipeline and stress audit
Date: 2026-11-01 UTC. **RESEARCH TRAINING ONLY — NOT INDEPENDENT OOS OR LIVE-TRADING APPROVAL.**

## Immutable original source and quality gates

- Authorized private historical Gold ZIP SHA256:
  `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
- It was retrieved and processed **locally** with no raw Gold quotes,
  broker secrets, trade ledger, or source archive added to public GitHub.
- Separate real-source BOS/H1 replay: **26/26 frozen report files
  byte-for-byte identical**, 2012/2017/2020/2024, 2,876 trades,
  **0/48 profitable months**, -$1,226.22560 per 1oz after the declared
  fixed $0.40/oz all-in completed-trade charge.
- Distinct historical 2012–2019 BOS/H1 execution parity: **3,800 trades
  matched on 13 required execution fields**, across 16 year/variant
  scenarios. Do not aggregate this with the distinct 2,876-trade study.
- Exact checked source snapshot was independently compared to the
  repository's five replay-critical module blob SHAs.
  See [detailed frozen audit](ORIGINAL_GOLD_OFFLINE_REPLAY_AND_3800_TRADE_PARITY_2026-11-01.md).
- **Latest exact-head GitHub CI at `f94ce6c3`:**
  [Engine quality gates run 41293588841](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41293588841),
  **3,366 pytest passed**. [Causal formula regression run
  41293588833](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41293588833)
  also succeeded. CI never received the private archive.

## Fresh private one-command arithmetic research run — passed

A brand-new, empty private output folder was used. The launcher
`python -m scripts.run_quant_research_platform` processed the
original ZIP with fixed **training years 2012 and 2013**, seed
`20261101`, **one generation**, **two generated formula candidates**,
shard size two, and the fixed **$0.40/oz all-in** fee.

- **4** original-source baseline annual backtests (2012/2013 ×
  reference/fast), verified before publishing the immutable seed.
- **8** original-source generated-formula annual backtests
  (two candidates × 2012/2013 × reference/fast), independently
  reconciled and materialized as immutable training feedback.
- **Total: 12 canonical real-source annual engine executions** for
  that fresh pipeline; each reference/fast pair passed the canonical
  source, execution and ledger matching gates.
- Full loop returned exit **0**, status
  `COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS`.
  One generation was completed; read-only dashboard reported
  **one verified generation, three compared strategies** (including the
  seed), **one matched-parameter comparison**, and SHA256
  `23b0e9bb0e263892d7b637ed459c84af4c410fd0d333339183b949e908c5ac5e`.
- A second, independently executed **resume/attestation** invocation
  successfully returned `REUSED_FULLY_REAUDITED_FEEDBACK` with
  **no duplicate market replays**.
- Seed formula on 2012–2013: 13/24 positive months,
  net **-$0.79/oz** (rejected). All formulas evaluated were still
  historical retrospective training-only candidates, not signals.

## Candidate failure analysis — frozen BEFORE additional-year results

The best training-only formula had exact identity
`6fb9497cb5cba73b45183fb1403085f80232e751757aeca1e030c05b5fbbd72a`.
On 2012–2013 it had **200 trades**, +$413.35/oz,
14/24 profitable months. It was **not** eligible for live trading.

Before evaluating additional years, a local immutable protocol pinned:

- The exact formula identity, SHA256 source ZIP, fixed parameters,
  reference/fast engines, fee, **2017 and 2024 historical stress years**
  and **zero parameter retuning**.
- A strong descriptive target: profitable in both additional years
  AND positive net P/L in **all 24 additional calendar months**.
- This is a **RETROSPECTIVE EXPOSED HISTORICAL STRESS**, *not*
  prospectively untouched out-of-sample research, because the
  historical archive has been used previously in other strategy work.

| Year | Additional trades | Positive months | Net USD / 1oz | Independent reference/fast check |
| --- | ---: | ---: | ---: | --- |
| 2017 | 34 | 9/12 | +198.52 | PASSED |
| 2024 | 196 | 5/12 | -237.02 | PASSED |
| **Total** | **230** | **14/24** | **-38.50** | **PASSED** |

**Result: REJECT.** The observed positive training score did not
generalize across the selected exposed historical stress years.

During the first stress attempt, one container copy of the archive was
unexpectedly truncated *after* loading 2017 data. Its persisted
reference report carried a different source-file SHA and was
**quarantined as invalid evidence**. The original ZIP was recovered
to a new location from the private Library, its full SHA256 and
all 17 JSON members' CRCs were rechecked; the affected 2017 replay
was re-executed, and the complete 2017+2024 reference/fast pairs
passed source fingerprint and accounting checks. The invalid
quarantined report was **excluded** from the final result.

To reduce the chance of a misleading future report from a changing
archive, the canonical `norisk backtest` now computes a
file SHA256 both **before** loading and **after** execution, and
fails if they differ *before publishing the report*. Regressions
cover a synthetic archive modified during loading and a stable archive.
This is not a defense against adversarial swap-and-restore races.

## Private operator runbook

Run only on an authorized machine with access to the original private
source archive, using Python 3.12 and constrained dependencies:

```bash
python -m pip install -c constraints-ci.txt -e ".[dev]"
python -m scripts.run_quant_research_platform \
  --gold-zip "/private/Gold data.zip" \
  --out "/private/norisk_quant_research" \
  --years 2012 2013 \
  --seed 20261101 --generations 10 --count 12 \
  --shard-size 8 --min-free-gb 2 --max-wall-seconds 7200
```

Use an **owner-only output directory outside the Git repository**.
Use an immutable root to resume **with the same original archive, seed,
first generation, proposal count, shard size, policy and training-year
selection**. To change immutable research identity, use a fresh root.
Read `platform_status.json` for the current phase and
`quant_research_dashboard.html` for the private
read-only candidate comparison. The launcher handles the initial
source-verified seed, local generation, reference/fast annual checks,
resume re-attestation, a final evidence dashboard and explicit
training-only outcome status.

**Resource caveat:** the wall-clock budget is checked between generations,
not a preemption deadline for a single annual backtest. This command runs
only while the local process is alive; persistent hosting or an authorized
OS job scheduler is required to make it recurring. It does **not**
automatically import untouched future data or certify tick fills.

## Explicit release blockers

1. No genuinely untouched forward/prospective out-of-sample data have
   established an edge after researcher selection and multiple tests.
2. No broker-specific tick fills, actual commission/spread/slippage or
   realistic margin liquidation validation.
3. Not all distinct strategy-factory, execution, interface and telemetry
   families have been independently integrated into this bounded
   *arithmetic research* one-command acceptance route.
4. 24/7 monitoring requires an actual continuously available local or
   privately authorized server process and schedule; GitHub public
   Actions cannot process the owner's private raw Gold ZIP.
5. No verified every-month profitable strategy, live signal approval,
   licensed investment-advice claim, or guaranteed returns.
6. Release remains a **Draft unmerged PR**, with the repository's
   public visibility unchanged and no billing/spending changes.

**Bottom line:** the auditable local historical mathematical research
pipeline is functional and source-verified, but it does **not**
establish the comprehensive live-capable platform or a profitable
strategy as finished.
