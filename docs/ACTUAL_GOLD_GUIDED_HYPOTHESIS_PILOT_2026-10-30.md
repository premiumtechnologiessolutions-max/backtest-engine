# No Risk FX — Opt-in feedback-guided research, original-Gold pilot (2026-10-30)

## Delivered architecture (current Draft PR)

An **opt-in**, deterministic `matched_guided_v1` proposal policy now connects the
previously separate matched-parameter diagnostic subsystem to the canonical
multi-generation research execution path:

`reconciled historical training → one-variable matched pairs →
training-only guided hypothesis proposals + diversity mutations →
immutable generation manifest → canonical dispatch → original Gold M1
Reference/Fast replays → independent annual/monthly/weekly/equity audit →
next immutable training input`.

The default `legacy_random` mode preserves prior frozen manifest bytes and
allows all earlier experiments to be replayed without reinterpretation.
The policy is exposed through `run_arithmetic_evolution.py`,
`run_arithmetic_research_cycles.py` and `research_campaign_supervisor.py`
with `--proposal-policy matched_guided_v1`.

**Safety:** The chosen favorable direction is **post-hoc historical training**,
not a causal market mechanism or independent OOS. Up to half of the proposal
slots can follow one-parameter, positive-annual-contrast training
hypotheses; remaining slots use the existing diversity mutator. Every
hypothesis carries its source-contrast SHA256; the canonical dispatch verifies
the entire generation deterministically against the original frozen training
input. A changed campaign policy requires a new immutable campaign root
rather than reusing stale results. All holdout fields are rejected.

## Actual original-source pilot — generation 8, two proposals

- Original private Gold ZIP SHA256:
  `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
- Initial frozen exposed-training input (20 previously evaluated parents)
  SHA256: `576b75d72ea5462524700e64ac31992cb628bf50992218d0ed44b0ac11680418`.
- **14** evaluated matched single-parameter training pairs were available.
  The deterministic generation proposed **1 guided** and **1 diversity**
  hypothesis. Its manifest was reproduced and audited against the original
  training input.
- Both proposals were executed on the previously inspected full 2012 and
  2013 Gold M1 years, 1 oz, **$0.40/oz ALL-IN per completed trade**, with
  separate Reference and Fast execution and complete annual accounting.
- **4 complete formula/year evidence shards** passed canonical report
  reconciliation; next-input SHA256:
  `2adc9e894fb6c39dc0f3c5e20d8081035d082af7f71ae21cc72979ac45e88609`.
  The frozen input was independently reattested, returning
  `CACHED_GENERATION_FULLY_REAUDITED_NOT_OOS` with 4 verified shards.

| Proposal | 2012 net USD/oz / trades / positive months | 2013 net USD/oz / trades / positive months | Separate-year total net USD/oz | Positive months |
|---|---|---|---:|---:|
| Training-guided | -7.15 / 517 / 8 | +308.96 / 638 / 7 | **+301.81** | 15/24 |
| Diversity | -15.96 / 13 / 4 | +144.65 / 21 / 6 | **+128.69** | 10/24 |

The guided proposal **FAILS** the frozen training screen despite 15 positive
months: **47 gap-exposed trades**, **2 forced end-of-data closures**, and
negative annual net in 2012. The diversity proposal likewise fails
(34 trades, 10 positive months, 22 gap-exposed trades, 2 forced closures).
No formula was approved for independent future OOS or live execution.
Results represent separate historical research years, **not** a continuous
portfolio or annualized return. Training comparisons have selection bias.

The original ZIP, private formula-level trade/equity ledgers and M1 source
bars remain **local only**. The GitHub repository is currently **PUBLIC**;
only this aggregate, non-trading report and synthetic contract tests are
committed. No raw source data, billing change, PR merge or live trade occurred.

## Verification and unfinished launch gates

Exact guided-policy branch commit
`5345759352b502d78320baf2837e9f901496df1b`:
[Engine quality gates](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41068192434)
**SUCCESS — 3,132 pytest passed**, including 7 opt-in guided-policy
regressions, and canonical synthetic Reference/Fast parity.
[Quant Lab causal regression](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41068192456)
**SUCCESS**. An unrelated local preflight on the full suite lacked the
optional parquet dependency `pyarrow` (8 local environment errors),
whereas the pinned GitHub CI completed successfully.

This pilot executed the locally reconstructed branch changes over the
original source and used exact canonical report parity. The latest source
check-out and GitHub CI are separate proofs; do **not** claim a full
newest-HEAD source re-clone/identity check from this pilot.

**Still not finished:** verified 1,000–10,000 strategy run with resource
telemetry; unattended 24/7 authorized worker/deployment; authenticated
and live multi-user platform; deeper failure-conditioned *causal*
experimentation; independent untouched prospective results and broker tick
checks. No strategy with a stable monthly edge was established.

## Local research command (private authorized machine only)

```bash
python -m scripts.run_arithmetic_research_cycles \
  --training-input /private/frozen_reconciled_training.json \
  --gold-zip "/private/Gold data.zip" \
  --out /private/research_runs \
  --seed 31 --first-generation 8 --generations 1 \
  --count 2 --shard-size 1 --proposal-policy matched_guided_v1
```

Never run this with source files or outputs inside the public Git checkout.
