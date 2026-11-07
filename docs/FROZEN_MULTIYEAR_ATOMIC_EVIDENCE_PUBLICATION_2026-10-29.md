# Frozen multi-year replay: atomic evidence publication (2026-10-29)

## Failure mode

The authorized-original-ZIP BOS/H1 annual sensitivity runner previously wrote
the first year's `trades.csv`, `monthly.csv`, `weekly.csv`, equity and
`summary.json` directly into the requested destination before subsequent years
and the final source archive SHA check completed. If a later year failed,
partial annual outputs remained and could be mistaken for a completed frozen
multi-year study. Absence of the combined summary alone was not a sufficient
fail-closed publication boundary.

## Change

`execute()` now validates the destination, creates a sibling temporary staging
directory on the same filesystem, and runs the **unchanged** actual annual
strategy/executor/audit/report stack there via `_execute_unpublished()`.
Only after all years pass, per-trade audits reconcile, annual CSVs reconcile,
and the final archive SHA is unchanged, the staging directory is published
with a single `os.replace()` directory rename.

On an exception, the staging directory is deleted and the requested
destination is left untouched. A destination that was nonempty at preflight
or becomes nonempty before publication is rejected; existing empty
destinations are supported. Existing ancestor symlink guards are preserved.
The replacement is an atomic filesystem rename on supported local
filesystems; it does not promise crash-durable fsync, network filesystem
atomicity, or protection against malicious concurrent directory swapping.

## Regression coverage

`tests/test_frozen_bos_atomic_publication.py` covers a later-year failure
after a synthetic earlier annual report exists, successful publication,
replacement of an existing empty directory, concurrent destination
population, and cleanup after a synthetic final-source-integrity error.
No original Gold ZIP, raw BID/ASK quotes, or new out-of-sample years were
opened or uploaded for these tests.

## Research interpretation

This is an **evidence integrity** change, not a strategy improvement.
Frozen BOS/H1 rules, execution policy, exact all-in $0.40/oz, and
historically exposed negative results are unchanged. Current-head replay
against the private original archive and 13-field historical parity are
still required. Draft PR #1 must remain unmerged until those checks pass.
