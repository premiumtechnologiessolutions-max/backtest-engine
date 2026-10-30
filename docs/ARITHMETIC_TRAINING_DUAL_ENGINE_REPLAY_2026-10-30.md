# Arithmetic Evolution → canonical dual-engine training replay

Date: 2026-10-30. Research-only; **not** independent out-of-sample evidence.

This runner is the next integration step after
`scripts/materialize_arithmetic_generation.py`. It verifies the original
training input and deterministic generation, materializes the frozen formula
dispatch, invokes the **actual** `norisk_quant.cli backtest` twice per selected
formula, then compares Reference and Fast outputs before atomically publishing
any result. No live trading interface exists in this workflow.

## Reproduction with the original private source

The private `Gold data.zip` remains on an authorized local machine. Never
upload it, private broker data, or credentials to GitHub.

```bash
python -m scripts.run_arithmetic_dispatch_training \
  --training-input /secure/training.json \
  --generation-manifest /secure/generation.json \
  --dispatch-dir /secure/frozen_generation_1 \
  --data "/secure/Gold data.zip" \
  --data-sha256 1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121 \
  --year 2012 --start-ordinal 1 --limit 8 \
  --out /secure/research/arithmetic_training_2012_1_8
```

**Only** the original Gold ZIP SHA above is accepted. The year must already
appear in the frozen evolution manifest's **training_years**. All 2012–2026
historically exposed samples remain research/training samples; the runner
cannot open a new holdout year merely by changing the command line.

The batch is intentionally bounded (default 8 formulas, maximum 128). Use
nonoverlapping ordinal ranges and **new** output paths for additional batches.
Each formula is run once through the Reference engine and once through the
Fast engine with identical data, one ounce, M1, and exactly $0.40/oz all-in
round-trip fee. Reports contain the original CLI trade, monthly, weekly,
minute-equity, gap, and summary artifacts for each engine.

## Fail-closed gates

1. Original ZIP fingerprint matches the preregistered source SHA before and
   after the run; generation replay matches the original frozen training
   input; each dispatched formula matches its SHA and formula identity.
2. The annual training sample must contain observed M1 in all 12 months.
3. Reference and Fast source fingerprints, selected headline metrics,
   accounting checks, 15 trade execution fields, every CSV trade row,
   monthly/weekly buckets, M1 equity marks, and gap catalogue must agree.
4. Per-trade cost is checked at exactly $0.40 times ounces, with reconciled
   trade, month, week, and annual net P/L.
5. Any subprocess failure, mismatch, or changed source removes the temporary
   staging directory and **does not publish** the requested destination.
   Existing evidence cannot be overwritten; output symlinks are rejected.

This is **cross-engine parity**, not independent validation against broker
ticks. Both engines may share a modeling assumption or data defect. The
historical archive cannot establish genuine prospective performance.

## Verification status and limits

The source and synthetic contract tests were added on 2026-10-30. At the
time of this documentation commit, the new runner **has not been executed**
against the original private Gold ZIP, and its new tests have **not yet been
confirmed by a GitHub CI result**. Previous successful CI runs on older
commits do not certify this integration. Keep PR #1 Draft until actual full
pytest/CI and original-archive replay parity pass.

This runner does not yet automatically feed audited results back into the
evolution controller; that requires a separate verified training-evidence
adapter and a controlled resume/retry ledger. It does not certify a profitable
edge, an independent OOS sample, or live-trading readiness.
