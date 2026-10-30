# No Risk FX Unified Research Platform — Phase 1 consolidation (B08)

Date: 2026-10-30. This is a **consolidated private-operator research stack**,
NOT a production deployment or a profitable automated trading system.

## Why this consolidation matters

B01/B03 strict NoRiskFX Terminal v0.19.1 intake was developed in a branch
separate from B04/B05/B06/B07 canonical research queue, original Gold ZIP
preflight and historical research worker. Independent green CI did NOT mean
that all these components were installed in the same Git checkout.

B08 takes the EXACT B07 Git source tree (which already contains B02, B04,
B05, B06 and B07) and adds the B01/B03 integration files, their regression
tests and workflows from PR #9. It retains the byte-identical B02
source_registry.py used in both histories. The future merge/rebase into
the central quant branch must be reviewed independently.

## Implemented private in-process status composition

`UnifiedResearchPlatform(queue=ResearchQueue(private_db))` exposes:
- `observe_terminal_snapshot(raw_bytes)`: one-time strict parser of
  PRIVATE MT5 read-only BID/ASK tick evidence and *in-memory* source
  registration. Does not copy quote arrays into public status or GitHub.
- `index_declared_source_manifest(manifest)`: read and verify the B02
  immutable SourceRecord envelope, explicitly without authenticating
  original Gold raw bytes in this layer.
- `operator_snapshot()`: one local operator-only view covering
  source metadata (original Gold M1 vs private Terminal ticks),
  private durable research task counts, paused status, and
  detailed source/science/privacy gates still outstanding.

## Three strictly separated research boundaries

1. **Source evidence**: input provenance only. Real Terminal quotes are
   NOT the original 2010–2026 user-supplied Gold historical M1 archive.
2. **Research intent and official execution**: Nova/Forge proposals
   use canonical experiment identity, source fingerprints and exact code;
   queue starts PAUSED, a private operator must explicitly resume. Only
   independently implemented built-in Gold M1-sweep research is eligible
   for B06 historical execution, subject to original ZIP review.
3. **Scientific confirmation**: no agent may claim broker fill parity,
   positive every-month returns, strategy approval, independent future
   holdout, audited market-calendar gaps, or live/paper eligibility.

## Privacy & authentication

The snapshot is an in-process **OPERATOR view**, not a public web
endpoint. It does NOT implement HTTP authentication or authorization.
The private Terminal server's existing gateway must protect it before
an authenticated API or UI is introduced. SourceRegistry remains
nonpersistent, while the research queue's SQLite is private local
persistent state. Do not place account numbers, credentials, original
Gold ZIP, raw broker ticks, AQL private DB or original trade ledgers in
PUBLIC GitHub.

## Review checklist

- [ ] Exact-head GitHub Actions Python3.12 Linux+Windows targeted and
      Ubuntu full-suite green after B01/B03+B04–B07 code coexist.
- [ ] B01/B03 original Terminal XAUUSD and EURUSD privacy samples verified
      OFFLINE in the owner's own environment (not synthetic CI).
- [ ] B07 original month manifest generated on exact source, and B06
      executed on SAME pinned canonical Git SHA locally with POSIX-only
      owner-only files and full month/week/trade reconciliation.
- [ ] Independently inspect original 2010–2026 multi-year source/import
      lineage and classify missing minutes vs market closures.
- [ ] Implement source manifest durable private storage, backups/restore,
      access controls and explicit read-only status API inside Terminal.
- [ ] Never authorize AQL FX strategies to execute native Gold rules
      before independent strategy implementation parity.
- [ ] Preserve scientific failures and prospective holdout rules. No
      profitability guarantee or automatic real-money trading.

Related Draft PRs: B01 #5, B02 #8, B03 #9, B04 #10, B05 #11,
B06 #12, B07 #13 and parent project issue #6.
