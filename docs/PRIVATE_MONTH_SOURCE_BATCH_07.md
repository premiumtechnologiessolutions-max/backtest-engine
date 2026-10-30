# Batch 07 — Private original-Gold monthly source preparation

Date: 2026-10-30. **Research-only; under Draft review.**

## New operator workflow

Batch 06's canonical research worker cannot run until a **frozen
month-specific data-source manifest** has already been supplied. It must
not silently generate a new source proof from the same experiment it is
about to execute. This batch adds a separate one-time *preparation*
command that generates the exact immutable B02 SourceRecord schema
required by B06.

On a private local **POSIX** research machine, make an existing owner-only
directory (mode 0700), then run BEFORE inspecting any new strategy result:

    python scripts/prepare_gold_month_manifest.py --source /private/GoldOriginal.zip --year 2012 --month 1 --out /private/research-manifests/2012-01.json

The script:
- Rejects open/future months, unexpected source format, missing/duplicated
  annual Gold JSON members, oversized annual source data and empty months.
- Uses canonical `load_market` and `validate_loaded_m1`, not a separate
  data importer, and preserves exact observed UTC Bid/Ask M1 timestamps.
- Recomputes original **whole-ZIP** byte SHA and the **observed monthly
  BID+ASK** price/timestamp SHA, row count and first/last observed timestamps.
- Requires first and last observation of the month to be within 72 hours
  of UTC calendar edges; this never invents bars or certifies that a
  holiday/weekend is a valid scheduled market closure.
- Produces the B02 source manifest as a private JSON with exclusive-create
  O_EXCL and POSIX 0600 permission; never overwrites existing evidence.
- Outputs to console **only redacted metadata**, explicitly marked
  `LOCAL_SOURCE_CANDIDATE_NOT_PREREGISTERED`, not source fingerprints,
  prices, private file paths, account scope, orders or trading P/L.

The operator must separately record the manifest's SHA and confirm it was
frozen before any new experiment: a valid source manifest is **NOT**
pre-registration of strategies or independent OOS.

## Integrated acceptance test
The B07 source manifest is consumed by the exact B06
`preflight_queued_research` route (Data Hub -> immutable canonical proposal
-> original ZIP replay -> frozen batch plan) on explicitly synthetic source
quotes. Mutation of the original ZIP then invalidates the old frozen
manifest before any backtest may run. Linux/Windows contract tests, and
a separate full canonical Linux regression, run in GitHub Actions.

## Separate private actual Gold experiment (NOT this exact Git commit)
A local **2026-10-26 operational snapshot** ran a historical EMA(9,21)
M15 reference backtest for January 2012 against the owner's actual
Gold data(1).zip. It generated trades.csv, weekly.csv, monthly.csv,
summary.json and passed that snapshot's internal accounting checker.
There were 53 completed trades, 18 wins, net -18.68501423237055 USD
for one ounce, and total fixed costs 21.20 USD. This is
**historical_exposed** and **synthetic reference BID-OHLC**, not broker
execution, not B06 m1-sweep, not an independently reproduced result
on the latest PR #12 SHA, and NOT a verified edge.

The private source, raw quotes, quote fingerprints, exact account scopes
and full local ledger stay OUT of the public repository. Private report
for the owner is held separately in the conversation workspace.

## Known blockers
- No end-to-end actual original Gold run at the exact PR #12 SHA yet.
- Native Windows/NTFS permission controls are not reviewed. This output
  command deliberately refuses non-POSIX execution.
- 2010–2026 exchange/holiday/calendar gap taxonomy is NOT complete.
- Cost model is the user-prescribed $0.40/oz all-in research assumption.
  It is NOT independently verified executable broker cost.
- AQL Nova/Forge foreign strategy code has not been independently mapped
  to an equivalent canonical Gold signal generator.
- Data-source validity alone does not validate strategy returns,
  selection bias, future OOS, paper/live eligibility or profitability.
- No Oracle deployment and no MT5 order access.

Related: stacked B06 Draft PR #12, B05 #11, B04 #10, B02 #8,
platform architecture epic #6.
