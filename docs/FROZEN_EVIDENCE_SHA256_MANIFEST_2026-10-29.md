# Frozen BOS/H1 annual evidence SHA256 manifest — 2026-10-29

## Problem and scope

The frozen annual runner already stages its multi-year reports and publishes them
only after strategy execution, source-bar audits, fee/period reconciliation and a
final original-source SHA check. A directory of CSV/JSON files can nevertheless
be altered, truncated, removed or supplemented **after** publication without an
explicit byte-level verification mechanism.

This change adds a deterministic `evidence_manifest.json` before publication.
It records the private source archive's **SHA256 fingerprint**, selected years,
and the relative path, byte count and SHA256 of every output file (excluding the
manifest itself). It does **not** embed raw M1 quotes or private trade rows.

## Fail-closed behavior

- Require `summary.json`, `trades.csv`, `monthly.csv`, `weekly.csv`,
  `equity_m1.csv`, and `gap_catalogue.csv` for **each** selected year,
  plus the combined `frozen_sensitivity_summary.json`.
- Reject missing, unexpected, changed, duplicated or unsafe-path manifest entries,
  symlinked files and symlinked manifest paths.
- Rehash the full staged tree immediately after writing the manifest. Any
  verification failure aborts publication and deletes the staging directory.
- A recipient can reverify a local report directory with:
  `python -m scripts.frozen_evidence_manifest --root /secure/reports/frozen_run`.
- The runner supports both module and direct-script invocation.

## Verification

The new `tests/test_frozen_evidence_manifest.py` tests synthetic evidence
roundtrips, same-size content tampering, added files, missing required reports,
symlinks, traversal attempts, source/year mismatch, and invalid year types.
The existing frozen runner synthetic integration test now verifies its
generated manifest. No original Gold ZIP or confidential quote data was used
for these checks.

Local standalone module tests: **11 passed** on Python 3.11 with pytest 9.0.2.
The repository-wide CI result must be checked separately against the final
commit before claiming full acceptance.

## Boundaries

This is a **detectable integrity inventory**, not a digital signature. A party
able to rewrite both the report files and manifest can forge a consistent set
of hashes; trustworthy attestation would need a separately held signed digest.
The manifest does not establish broker tick fills, official market closure,
independent OOS, monthly profitability, or source archive availability.
No strategy or $0.40/oz fee change. Draft PR #1 remains unmerged; the repo is
currently public despite the requested private designation.
