# No Risk FX — Batch 10 private original Gold replay handoff

Date: 2026-10-30. Research audit only. **No broker connectivity, no orders.**

## Why this exists
All B09 code-based GitHub CI is green, but the owner-supplied original
Gold data(1).zip has never been executed against that exact SHA. The
local execution container cannot resolve github.com and importing the
private 149MB ZIP into any public repository, CI log, CI artifact, cloud
runner or third-party source would violate the private-data boundary.

## Exact commit source handoff
The new GitHub Actions workflow fetches the **pull-request HEAD** (not a
GitHub-generated merge SHA), with `persist-credentials: false`. It creates
a standard Git bundle containing the exact commit and ancestors. It
verifies a fresh clone and identical Git SHA on the runner. A 7-day
artifact contains:
- `exact_commit.bundle`: source code and Git history, NEVER private prices.
- `exact_commit.txt`: source revision checked by Actions.
- `bundle_sha256.txt`: expected bundle byte hash.

The bundle contains the repository's **Git history**, not private Gold
data. Review historical repository confidentiality before distributing
the bundle to anyone else. It must stay outside any publicly served
Terminal assets.

## Private local operator verification
After retrieving the artifact to the owner's machine, extract the Git
bundle. Verify SHA256 against bundle_sha256.txt and clone it:

    sha256sum -c bundle_sha256.txt
    git clone exact_commit.bundle /private/nrfx-exact-head
    git -C /private/nrfx-exact-head rev-parse HEAD

The result MUST match exact_commit.txt. On a private POSIX research host
with Python 3.12 and dependencies pinned by constraints-ci.txt, use the
existing B07 source-manifest preparer, original private data ZIP, B04
paused queue and B06 one-job runner:

    python scripts/prepare_gold_month_manifest.py --source /private/GoldOriginal.zip --year 2012 --month 1 --out /private/manifests/2012-01.json

    python scripts/canonical_research_worker.py --queue-db /private/research.sqlite3 --resume
    python scripts/canonical_research_worker.py --queue-db /private/research.sqlite3 --execute --source-manifest /private/manifests/2012-01.json --original-gold-zip /private/GoldOriginal.zip --checkout /private/nrfx-exact-head --private-output /private/results

B09 worker now independently reattests on-disk individual trade CSV,
weekly/monthly CSV, summary settings, immutable original ZIP SHA and Git
revision BEFORE committing the queue artifact digest. No source ZIP or
price data may be uploaded to GitHub.

A queue experiment must ALREADY exist and must reference the **exact**
Git commit and original archive SHA and valid month/source parameters.
The queue starts paused; if the operator has not frozen and submitted
an experiment, invoking --execute returns no research job. Outputs are
historical-exposed synthetic-reference simulation, NOT broker tick fill
parity, independent OOS or profitability evidence.

## Release checklist
- [ ] Download and independently verify exact-head source bundle.
- [ ] Prepare per-month private original-source manifest on exact checkout.
- [ ] Execute one SOURCE-AND-REVISION matched real original Gold month.
- [ ] Re-run B09 offline independent file audit with results held private.
- [ ] Archive expected SHA and check actual monthly/week/trade totals.
- [ ] Independently verify the multi-year calendar-gap taxonomy and
  forward-selection/OOS protocol.
- [ ] Revisit Windows native NTFS ACL protection before any deployment.
- [ ] Separate authenticated Terminal read-only API, backups and restore.

**Never** mark profitable models or real-money trading approved based on
passing CI or historical M1 alone. PR remains Draft.
