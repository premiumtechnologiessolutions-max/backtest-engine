# No Risk FX Quant Research — five-system integration milestone (2026-10-30)

This development moves the existing original-Gold-tested, 2-generation
research loop toward a full research platform. **It is not finished**:
independent forward outcomes, actual distributed execution, always-on worker
deployment and production UI/service acceptance remain open.

## 1. Thousands of strategies / resource management

The earlier 128-*lifetime-candidate* cap prevented indefinite research:
after enough generations, the immutable feedback bridge could not publish
another generation. The new `research_candidate_memory.select_training_memory`
reconciles every candidate's complete frozen training years, ranks only
training evidence and retains the best **128 active breeding parents**;
**all** evaluated identity hashes remain in `explored_ids`, including
evicted formulas, so nothing is silently rediscovered.

The feedback bridge retains its **byte-identical historical output path**
when no compaction is needed (<=128). When a generation crosses 128, its
evidence sidecar explicitly records selection method, universe size, retained
count, all evicted identities, training scores and diagnostic reasons, never
prices or trade ledgers.

One generation is still limited to 128 proposals, and the explored history
is currently limited to **100,000 identities**. This supports thousands
**over successive generations**, but has not been measured as a
10,000-candidate production benchmark. It is serial, not distributed compute.

## 2. A training-only failure-analysis brain

`research_candidate_memory.py` assigns deterministic, auditable
**descriptive** diagnoses from independent training accounting:
insufficient trades, nonpositive net, fewer than 60% positive months,
a nonpositive training year, gap exposure and forced end-of-data closures.

These are *observable characteristics*, not proven reasons for market
failure, not self-directed scientific causal inference, and not a promise
that a proposed mutation will improve outcomes. The generation mutator
still provides hypothesis variation; there is no trained LLM agent.

## 3. Resource budgets, restart and operational status

`scripts/research_campaign_supervisor.py` calls the canonical original
ZIP backtest, reference+fast audit and immutable feedback loop **one
generation at a time**. It records `campaign_status.json` after each
generation, checks free disk space and a wall-time budget **between**
generations, and re-verifies immutable feedback prior to reusing a
completed generation. It uses a cross-platform exclusive batch lock to
prevent concurrent campaigns sharing an output root.

This is a **synchronous** local program; it is not scheduled, deployed,
running continuously, or capable of aborting a single long backtest at
the wall-time boundary. Actual 24/7 operation requires an owned
authorized worker/host and service supervision. No broker contact.

Example (private machine, not inside Git):

```bash
python -m scripts.research_campaign_supervisor \
  --training-input /private/training.json \
  --gold-zip "/private/Gold data.zip" \
  --out /private/research_campaign \
  --seed 19 --generations 10 --count 12 --shard-size 8 \
  --min-free-gb 2 --max-wall-seconds 7200
```

## 4. Research dashboard / comparisons

`scripts/research_training_dashboard.py` reads published
`next_training_input.json` and its immutable evidence sidecar,
cross-checks the SHA, source fingerprint and TRAINING ONLY controls,
recomputes candidate scores and writes searchable, styled **private
static HTML**, with generation, net USD/oz, positive months, month-end
drawdown and failure diagnostics. Incomplete generations are shown as
not certified, never falsely ranked.

This is an offline comparison UI, **not** yet an authenticated, live-updating
multi-user platform. Never publish private dashboard reports/quotes
to the current public GitHub repository.

## 5. Independent validation protocol

`scripts/freeze_prospective_validation.py` may write an immutable,
publish-once prospective plan **before** any future period starts.
It only includes candidates which passed the complete training heuristic,
records the frozen formula/period/fee and explicitly marks OOS as
**not executed**. No candidate may be promoted merely for profitable
exposed training.

If none qualifies, its explicit result is
`NO_ELIGIBLE_TRAINING_CANDIDATES_NO_OOS`. The historical 2012–2013
two-generation experiment has **no qualifying candidate** under the
current training heuristic. Therefore no independent OOS result exists.
Outcomes cannot be verified until future data are genuinely unseen.

Example for a future date, without executing holdout:

```bash
python -m scripts.freeze_prospective_validation \
  --training-input /private/verified_training_input.json \
  --start 2026-11-02 --end 2027-01-29 \
  --out /private/frozen_prospective_validation.json
```

## Verification / no false acceptance

- Pure candidate-memory tests cover 160 distinct historical candidates
  compacted to 128 active and 160 retained identity hashes.
- Feedback contract tests cover a full **129-candidate** synthetic,
  reconciled replay-to-feedback generation and immutable replays.
- Campaign tests exercise interruption, restart, disk budgets, locking
  and never treating cached output as confirmed without verifying proof.
- UI tests cover evidence SHA tampering, incomplete generations and
  rejected OOS promotion.
- Validation tests check genuine future-only registration, lack of
  qualified candidates, immutable publication and source tampering.
- **These new tests use synthetic fixtures**, not thousands of real-Gold
  executions. Existing earlier two-generation original-source replays
  still mean two studied years and one newly tested formula per
  generation, **not** new OOS evidence.
- Fixed **$0.40/oz all-in**, PR remains **Draft/unmerged**.
  GitHub metadata currently reports **PUBLIC**, despite requests naming
  the repository private. Do not upload raw original Gold ZIP, quotes,
  trade/equity ledgers or private campaign data.

## Remaining launch gates

1. Run a multi-hundred / multi-thousand real-source candidate campaign
   with verified time, RAM/disk budgets and published aggregate receipts.
2. Implement robust checkpoint/lease/error telemetry per worker and
   a production service/runner with explicitly authorized 24/7 hosting.
3. Develop deeper research-adaptive diagnostics (mechanistic market
   hypotheses rather than only training outcomes).
4. Complete authenticated, responsive, live-updating integrated UI.
5. Freeze truly untouched prospective validation, wait for those observations,
   then run exact source and broker tick checks without post-hoc refitting.
