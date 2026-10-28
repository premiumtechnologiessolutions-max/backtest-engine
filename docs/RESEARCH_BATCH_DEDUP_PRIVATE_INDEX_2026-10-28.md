# Frozen batch exact-spec deduplication and private index — 2026-10-28

## Change

The historical-exposed batch orchestrator now refuses to expand two jobs with
the **same canonical validated strategy specification**, even if they use
different IDs or separate grid prefixes. This prevents accidental duplicate
canonical M1 executions inside one frozen plan and prevents inflated job counts.
The comparison covers strategy, timeframe, execution, dates and exact supplied
parameters. It does **not** collapse semantically equivalent defaults or
correlated parameter configurations, and it does **not** claim independent
hypotheses.

The offline monthly research index now uses the already tested atomic
owner-only HTML exporter rather than direct `Path.write_text`. This protects
local result links against a pre-existing symlink, writes with 0600 permissions
on POSIX, and preserves an earlier valid index on a failed atomic replacement.

## Verification and limitations

Five synthetic regression tests cover duplicate explicit jobs, job/grid
collision, grid/grid collision, private HTML export and symlink rejection.
These are tests of control-plane correctness, **not** original-source M1
replays. Current-head GitHub Actions CI must be checked separately after the
commit. The registry is unchanged because no new historical batches or
monthly P/L observations were produced.

This guard is **per frozen plan**, not a global deduplication index across
the strategy factory registry. No new profitability, prospective OOS,
broker tick, or shared-capacity portfolio claim is made. Keep PR #1 Draft.
