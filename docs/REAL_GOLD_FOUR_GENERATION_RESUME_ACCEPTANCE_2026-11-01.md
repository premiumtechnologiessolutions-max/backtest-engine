# Original-Gold four-generation integrated research acceptance — 2026-11-01

## Scope and result

**PASS for bounded historical training pipeline and immutable resume; NOT a
verified profitable strategy, broker execution, or independent OOS.**

The user's privately held original `Gold data(1).zip` was used **offline**.
Archive SHA256:

`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`

Experiment controls (frozen prior to results): years **2012 and 2013**,
`seed=20261101`, `generations=4`, `proposal_count=2`,
`shard_size=2`, `min_free_gb=0` for this local acceptance environment,
`proposal_policy=legacy_random`, canonical **$0.40/oz ALL-IN** cost.
Original historical years are **already exposed**; none is an independent
prospective holdout.

- The one-command pipeline `scripts.run_quant_research_platform` completed
  `source -> immutable real-Gold seed -> generation -> reference/fast
  backtest -> accounting/quote parity and ledger audit -> verified feedback
  -> next generation -> read-only research dashboard`.
- Final full fresh extension: **exit code 0**,
  `COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS`; all **4 of 4**
  generations have independently SHA-fingerprinted feedback.
- Generated hypotheses evaluated: **8** (2 per generation);
  **32 formula/year/engine replays** (4 generations × 2 formulas × 2 years
  × reference/fast). The real seed also evaluated 1 baseline for 2 years
  with both engines. At the final generation, **9 active historical
  candidates** were present.
- Highest retrospective net-P/L candidates:
  **+$490.51/oz over 2012–2013, 13/24 positive months** and
  **+$413.35/oz, 14/24 positive months**. Both **REJECTED** by
  training screening, including uncertain quote-gap exposure,
  forced end-of-data closure and insufficient positive months.
- None achieved 24/24 positive months; none was approved for live trading.

## Real failure discovered and fixed

The initial multi-invocation attempt failed while beginning generation 2:
`run_arithmetic_research_cycles.run_cycles()` rejected the previous
generation's canonical `next_training_input.json` solely because it
lived within the research results tree. That blocked a real supervisor
after one generation, even though a synthetic two-generation execution in
one call had passed.

Fixed by commit
[`ac4cc715`](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/ac4cc715d79a95b4eeef4fef218c4d07afcd8c9c):
allow only `generation_{N-1}/next_training_input.json` to seed generation
`N`; still reject arbitrary files, skip-a-generation inputs, and symlinks.
Added synthetic regression in commit
[`0ca6f85b`](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/0ca6f85bfc4d4758971bdef984f22146f1d46225).

The actual four-generation campaign then completed. A **separate complete
second invocation** rechecked all four generations with status
`REUSED_FULLY_REAUDITED_FEEDBACK` on **each of 1, 2, 3, and 4**,
without re-running completed market backtests. Status stayed marked
`TRAINING_ONLY` and `INDEPENDENT_OOS_PROVEN=false`.

## Snapshot and CI provenance

The local executed snapshot has Git blob hashes matching the PR branch
HEAD `eb89cc65147cbf6439c8d760790133c2df3ee9e1` for nine
critical entry points/modules: `run_quant_research_platform.py`,
`bootstrap_arithmetic_training.py`, `research_campaign_supervisor.py`,
`run_arithmetic_research_cycles.py`,
`run_arithmetic_dispatch_training.py`,
`research_training_dashboard.py`, `run_arithmetic_evolution.py`,
`compile_arithmetic_training_feedback.py`, and `norisk_quant/cli.py`.
This is a module-level byte identity check, **not** blanket certification
of all repository bytes or of broker execution.

[Engine quality gates run 41293756451](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41293756451)
on that HEAD: **3,366 pytest passed**.
[Quant Lab causal formula regression run 41293756524](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41293756524):
SUCCESS. GitHub Actions did **not** receive the private Gold ZIP.

Private local browser dashboard SHA256:
`c1f37d29c96af3a4f5a9c802422dd20f41bedf2af6398edca645f4698e66bda9`.
A minimal user-accessible ZIP contains only dashboard HTML and research
summary JSON, no private market ZIP, trade-by-trade prices, or equity
history. These private local output files are not committed.

## Unclosed release gates

1. A **genuinely untouched forward** evaluation remains necessary to
   distinguish market edge from multiple-testing / historical overfitting.
2. Broker-specific tick sequence, order queue, liquidity, margin,
   commissions/slippage outside the model assumptions, and live/paper
   trade behavior remain unverified.
3. Operating the platform continuously on its intended dedicated
   infrastructure with monitoring, recovery, and many thousands of jobs
   is a distinct scale/soak gate; four bounded generations do not establish
   that capacity or availability.
4. The historical training models here failed the intended strict
   monthly-consistency goals. Never advertise or infer a guaranteed
   monthly-profit strategy.

The repository remains GitHub **PUBLIC**; no source archive or private
results were pushed; no PR merge, billing change, or trading authorization.
