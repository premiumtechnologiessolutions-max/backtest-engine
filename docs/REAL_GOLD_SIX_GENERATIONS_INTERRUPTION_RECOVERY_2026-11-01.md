# Six-generation original Gold campaign, interruption recovery, and large-universe planning — 2026-11-01

## Exact real-source scope

The user's private original `Gold data(1).zip` SHA256 was verified:
`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
The market data was used **offline** and never uploaded to this GitHub
repository (which GitHub metadata identifies as PUBLIC).

Frozen research controls: **2012 and 2013 historical training**, seed
`20261101`, 2 generated formulas per generation, shard size 2,
6 generations, fixed **$0.40/oz all-in completed-trade fee**,
`legacy_random` proposal policy. All years in this research were
previously exposed; this is **NOT an independent forward/OOS experiment**.

### Completed integrated results

- Real pipeline output status:
  `COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS`.
- **6/6** generations finished with their immutable training feedback.
  **12** generated formulas (2 per generation) were evaluated in
  **48** formula/year/engine runs (2 years × reference and fast × 12).
  The separate initial baseline was also replayed with both engines.
- **13** final active historical candidates; **0** passed all training
  eligibility requirements. The two top historical P/L figures, **+$490.51**
  and **+$413.35 per ounce**, correspond to only **13/24** and **14/24**
  positive months, respectively. Both were rejected, also due to
  uncertain quote-gap and forced-end-of-data exposure.
- Dashboard SHA256:
  `109bed5ba3fc92a7b91898dd935058604f6384a59d3fbf7e3c29f6338b5c7ced`.
  Private dashboard contains comparative metrics only; the archive and
  individual trade/equity ledgers are not committed.

### Genuine interrupted-run recovery

A bounded external execution timeout terminated the attempt at
generation 6 before the 2013 annual shard finished. The canonical replay
executor's existing atomic publication meant the incomplete shard was
**never accepted** as a completed result. However, SIGKILL/SIGTERM left
a hidden staging folder of approximately **133 MB** on disk.

A new guarded recovery path (introduced after this observation) detects
interrupted `.nrfx_arithmetic_training_*` folders under the exclusive
research lock, validates the staging tree for suspicious links/nodes and
moves it into a private owner-only `.quarantined_training_staging`
directory. **It preserves forensic bytes** instead of deleting or
re-certifying incomplete evidence.

The real continuation rechecked generations 1–5, quarantined the
unfinished generation-6 temporary directory, replayed the missing
2013 shard, and then completed generation 6. On a **separate subsequent
invocation**, **all six generations** returned
`REUSED_FULLY_REAUDITED_FEEDBACK`, with no completed strategy
backtests repeated. The dashboard again matched its recorded SHA.

### Independent eligibility gate for future observations

The existing source/evidence-verified prospective freeze was executed
against the *sixth*-generation feedback, for a future 2027-01-01 through
2027-12-31 UTC window, 30-day embargo, no data access. It produced:

```text
NO_ELIGIBLE_TRAINING_CANDIDATES_NO_OOS
candidates_selected = 0
prospective_data_accessed = false
independent_oos_proven = false
live_trading_authorized = false
```

Freeze JSON SHA256:
`ae1e6b4917f43a96a5271700424d1dda61168eedfa3bf1324b15ddda20d1bee3`.
There is **no eligible formula** to deploy in this prospective study.

### Large research factory planning capacity

Additional real source-code dry-run probes expanded 20,000 and 50,000
**distinct** EMA parameter specifications and IDs without reading any
market file: 20k ~2.461 seconds / peak Python traced allocations
18.135 MiB; 50k ~6.040 seconds / 42.597 MiB. These are local
machine measurements of **specification planning**, NOT proof of
executing 50k market backtests or 24/7 production operations.
See `docs/QUANT_SCALE_AND_PROSPECTIVE_PROMOTION_GATES_2026-11-01.md`
and `scripts/research_scale_planning_benchmark.py`.

## QA provenance and limitations

The relevant GitHub branch implementation has new regression tests
covering bounded quarantine, no silent deletion, symlink attacks,
name collisions, and recovery of missing shards while leaving accepted
shards untouched. Local targeted test subset: **44 passed**.
GitHub Actions on exact commit
[`9582e739`](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/9582e739098baeb002be9f95868e9fad635575d6)
passed [3,390 pytest tests](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41295330532);
the Quant Lab formula regression workflow also passed.
CI uses synthetic fixtures and does not access the private Gold ZIP.

The local real-source continuation used matching code for the
`run_arithmetic_research_cycles.py` module at Git blob
`ef63b750f188e87109c2025010b157738d3e72d6`.
This is not a claim of byte-for-byte parity of **all repository modules**
or broker-level execution.

### Release blockers remain

1. No genuinely untouched, *prospectively registered* evaluation of an
   eligible formula has demonstrated persistent market edge.
2. No broker tick sequencing, live/paper fills, queue, margin,
   market impact, or live trading certification.
3. Actual 20k–50k historical backtest throughput with bounded parallel
   resources, repeated crash recovery and many-day runtime monitoring
   remains unmeasured. Planning those jobs does not perform them.
4. There is no demonstrated strategy or portfolio that profits in
   every month. No monthly-profit guarantee is scientifically defensible.

Keep PR #1 Draft/unmerged. No spending, visibility or live-trading
configuration was changed in this session.
