# Frozen annual evidence: prepublication file allowlist (2026-10-29)

## Threat model and correction

A SHA256 manifest detects later changes to files that it lists, but **does not
establish that each listed file is appropriate to publish**. Previously,
`write_evidence_manifest` would include arbitrary extra staged files in its
inventory. A stray original market archive, raw tick CSV, unrequested year, or
unreviewed note could therefore accompany the frozen annual report without
failing the manifest creation gate.

The official annual publication path now accepts **exactly**:
- `frozen_sensitivity_summary.json` at the root; and
- `summary.json`, `trades.csv`, `monthly.csv`, `weekly.csv`,
  `equity_m1.csv`, and `gap_catalogue.csv` under each selected year.

Both prepublication manifest creation and later verification reject unexpected
files, in addition to missing, altered, linked, or duplicate inventory records.
The check does not whitelist filenames in unrelated research workflows.

## Verification scope

Synthetic regressions cover accidental `Gold data.zip`, raw tick exports,
unrequested years, unreviewed root notes, hidden nested files, and a clean
allowlisted report. No private market data were included in the commit.

This is **not** proof that the repository is private, that the published
evidence is authentic, or that fills are executable. GitHub repository
visibility must be checked separately. The original Gold ZIP's 13-field
replay parity on the current HEAD remains outstanding. Keep Draft PR #1
unmerged until all research gates pass.
