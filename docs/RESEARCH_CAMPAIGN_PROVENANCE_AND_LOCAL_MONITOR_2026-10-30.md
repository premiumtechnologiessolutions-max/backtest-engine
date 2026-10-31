# No Risk FX — Campaign provenance and local research monitor (2026-10-30)

## Reliability fix: never reuse a different experiment

`scripts/research_campaign_attestation.py` is integrated into the
existing `scripts/research_campaign_supervisor.py`.

### Campaign intent freeze

Before first generation, `campaign_intent.json` is published once. Its
immutable canonical hash establishes:

- Original frozen training-input **byte SHA256**
- Preregistered original Gold ZIP SHA256
- Seed and starting generation
- Per-generation proposal count and annual shard size
- `TRAINING ONLY`, `NOT OOS`, `NO LIVE TRADING` flags

A resume that changes a frozen field is **rejected before accepting
cached results**, and needs a distinct campaign root. Runtime time/disk
limits and a longer generation horizon may still change without
changing experiment identity.

### Cached generation re-audit

A cached next-generation JSON SHA **alone** is not enough. To reuse
a completed generation the system now:

1. Replays the deterministic original training input and immutable
   generation manifest.
2. Verifies its exact generation, seed and formula count.
3. Rechecks canonical materialized formula JSON identities and hashes.
4. Re-runs the existing independent `compile_feedback` audit on all
   persisted annual reference/fast trade, monthly/weekly and observed M1
   equity reports. Missing/corrupted shards hard-fail.
5. Confirms the newly re-audited next-generation digest matches the
   immutable input sidecar.

This trades some resume time for reliable provenance. Large-campaign
resume performance still needs measured load testing.

**Actual-source audit:** a third-generation persisted original-Gold
training result (two annual replay shards) was independently re-audited
from the locally reconstructed attestation implementation, and
returned `CACHED_GENERATION_FULLY_REAUDITED_NOT_OOS`, with input
SHA `6900758c720521077cd3f98f06e7712dcaf79b323924eb33e88bdd570af7e24c`
and next-input SHA
`f4c197b3405ae16ba742d163721feda0844a0dd94926fe8cec94056a4644e4fc`.
This was a local offline re-audit of the source-artifact snapshot; do
not confuse it with a new exact GitHub HEAD original-source run.

## Local-only live control plane

`scripts/research_local_monitor.py` starts a read-only HTTP monitor
**bound exclusively to 127.0.0.1**, with three GET endpoints only:

- `/`: searchable HTML strategy comparison / campaign monitoring
- `/api/status`: sanitized completion and UTC freshness status, stale
  marker for `RUNNING_OBSERVED` older than 10 minutes
- `/api/generations`: SHA-checked aggregate training comparisons via
  the existing `research_training_dashboard.read_evidence`

Every other URL (including a ZIP path) returns 404. No write API, no
broker endpoint, no raw quote or individual trade ledger served. HTTP
responses disable caches, deny frames and include content restrictions.

Example on the **authorized local machine** (not a cloud deployment):

```sh
python -m scripts.research_local_monitor \
  --campaign /private/research_campaign --port 8765
```

The screen opens only on `http://127.0.0.1:8765/`.
It is **not** an authenticated remote multi-user production platform
and is not yet a deployed 24/7 service.

## Verification and remaining boundaries

- Added synthetic regression tests of immutable intent, altered seed,
  altered training file, altered formula, missing annual shard,
  forced re-audit, stale status, and an actual loopback HTTP request
  that proves the URL allowlist.
- The full CI suite must be checked for the *exact* final branch HEAD,
  not inferred from a previous green workflow.
- Original source data and all detailed trade/equity reports remain
  local/private; GitHub metadata says the repository is **PUBLIC**.
- This operational hardening does **not** prove a profitable edge,
  independent OOS, broker tick fill parity, or deployment of a
  perpetual cloud worker. PR stays Draft.
