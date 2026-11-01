# Research capacity and prospective-promotion gates — 2026-11-01

## Capacity probe: verified specification PLANNING, not execution

A local read-only expansion was executed against the actual
`scripts.research_batch_orchestrator.expand` and `run_plan(dry_run=True)`
logic, without any market archive, broker access or real backtests.
The source path was deliberately nonexistent.

| Probe | Unique strategy specs and job IDs | Python tracemalloc peak during expansion | Elapsed for expansion |
| --- | ---: | ---: | ---: |
| 20k | 20,000 / 20,000 | 18.135 MiB | 2.461 s |
| 50k | 50,000 / 50,000 | 42.597 MiB | 6.040 s |

- 20k plan SHA256: `cd522b3413474d65ab57034108aac7ed07af1246bf7b7559d805aa37de990a0a`.
- 50k plan SHA256: `f902a16c1649fee722d6ded2869973ff4d21fc4d6e3db13a9bc9e4d88e8ee6d9`.
- Jobs are valid frozen unique **EMA strategy parameter specifications**,
  NOT independent discoveries, completed annual backtests, empirical
  fill results or proof of 50,000-run throughput.
- The per-invocation planner budget was 500 defined jobs: 40 or 100
  invocations would be required *if* all jobs were ever executed, ignoring
  execution time and the additional audit costs.
- The probe instrumented Python allocations with `tracemalloc`;
  these figures do not represent total OS RSS, data cache, concurrent
  workers, subprocess memory or real market replay resource use.
- Regression test: `tests/test_research_scale_planning_benchmark.py`.
  No spending, market-source read or repository visibility change.

## Prospective registration from original-source four-generation results

Executed the existing fail-closed `freeze_training_selection` command
against the authentic immutable fourth-generation feedback from
the already-audited 2012–2013 Gold training campaign.

Proposed **future calendar:** 2027-01-01 through 2027-12-31 UTC,
created 2026-11-01, 30-day declared training embargo,
cost fixed **$0.40 per ounce ALL-IN**.
Result:

```
status = NO_ELIGIBLE_TRAINING_CANDIDATES_NO_OOS
candidate_count = 0
prospective_data_accessed = false
independent_oos_proven = false
live_trading_authorized = false
```

The publish-once prospective freeze JSON SHA256 is
`74bf3fbaf5ed30be0a5c312079fa4974f3c6e5867dd4242a70403e9aa98b402d`.
A freeze that selects **zero** eligible candidates does not constitute a
forthcoming OOS test, edge, live trade plan, or authorization to try a
failed candidate. The 2027 dataset is not yet available as of 2026-11-01.

## Release state

The existing genuine-Gold four-generation campaign and immutable resume
were verified separately; no validated strictly profitable monthly
portfolio or broker-specific fill track record exists.

**Engineering acceptance:** complete four-generation historical training
and 50k parameter planning capacity.

**Remaining:** actual thousands-of-backtests runtime soak with resource
measurements, independent prospective holdout of an eligible preregistered
candidate, and broker/tick execution acceptance. The historical search
has not found such an eligible strategy. Keep Draft PR #1 unmerged and
do not confuse successful planning with running thousands of backtests.
