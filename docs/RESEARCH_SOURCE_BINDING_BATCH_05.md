# No Risk FX Unified Research Platform — Batch 05

Date: 2026-10-30. Status: PRIVATE, read-only source-to-experiment integrity
preflight under review, NOT a trading or profitability verification.

## Motivation and source ownership
The canonical XAUUSD ExperimentIdentity (B04 PR #10) originally accepted a
declared source SHA. The Data Hub (B02 PR #8) stores a separately hashed M1
source and exact loaded BID/ASK quote SHA. A synthetic AI proposal could
otherwise reference any plausible 64-digit source SHA. Batch 05 consumes
B02's strict SourceRecord verification, checks actual local source bytes,
rechecks all eight M1 BID/ASK columns, checks UTC bounds and pinned engine
commit identity, and refuses to execute anything.

## Two different levels of provenance
- research_source_preflight.preflight_gold_m1_source: caller provides an
  original source-file path AND a separate canonical loaded M1 DataFrame.
  It hashes both and verifies metadata, prices, date range and proposal
  identity. IT DOES NOT prove that the loaded frame came from that archive;
  lineage_verified=False, even if both individual hashes match declarations.
- research_source_loader.preflight_direct_gold_m1_file: ONLY a direct
  original .json or .csv M1 input, <=80MB; it reads and normalizes the
  exact same file that it fingerprints. Because the source->frame path is
  directly executed, lineage_verified=True **for that file only**.
  It STILL does not authenticate the upstream broker, license the data,
  classify trading-session gaps, ensure independent OOS, or prove P/L.

The user's original multi-year Gold ZIP / imported Parquet partitions are
not eligible for the direct-file lineage claim. Before original large-data
research can execute, build an importer-specific archive SHA + partition
manifest + observed slice fingerprint linkage, with private local replay.
Do not claim B05 has certified the user's original 2010–2026 archive.

## Other gates
- source family MUST be original_gold_m1_bidask; Terminal broker tick
  evidence or SYNTHETIC source cannot replace user M1 history.
- engine Git full 40-character commit is checked against the proposal.
  inspect_local_checkout() observes an exact clean TRACKED Git checkout
  and rejects dirty tracked files and subdirectories. Untracked data or
  installed dependencies still require independent security review.
- source SHA is computed from raw file bytes; loaded M1 fingerprint includes
  exact UTC minute opens + all 8 BID/ASK price columns.
- observed M1 row count and full source start/end match the Data Hub
  manifest exactly. The requested experiment interval must lie within
  source history and contain at least one observed bar.
- separate fixed canonical $0.40/oz all-in cost remains the experiment
  contract, NOT an additional market-data fee.
- only data identity and source lineage are checked. Strategy mapping,
  scientific validity, cost/ledger parity, gap classification and execution
  approval remain BLOCKED.

## Offline CLI, direct sources only
    python scripts/preflight_ai_research_source.py --proposal PRIVATE_PROPOSAL_JSON --source-manifest PRIVATE_MANIFEST_JSON --original-m1 PRIVATE_ORIGINAL_M1_JSON_OR_CSV --checkout CLEAN_CANONICAL_GIT_ROOT

Outputs descriptive status ONLY (experiment ID, source manifest ID,
range and non-execution flags), never original ticks, prices, SHA of source
file, credentials, private paths or strategy P/L.

## Integration and review
- Built on B04 Draft PR #10 and copies B02 verified Source Registry module
  and its regression tests as a TEMPORARY stacked inclusion.
- Reconcile this repeated B02 file once B02/B04 are integrated into a single
  pinned baseline, preserving immutable manifest identity. Do not merge
  divergent versions or silently regenerate fingerprints.
- No Oracle deployment, source-data upload, broker calls, agent execution,
  real live/paper trading or production service modification.
- Must pass Linux+Windows pinned Python targeted CI and full canonical suite.
