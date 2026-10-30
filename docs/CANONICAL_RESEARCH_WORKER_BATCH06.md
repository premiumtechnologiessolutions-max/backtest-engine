# No Risk FX Unified Research Platform — Batch 06

Date: 2026-10-30. Draft, private offline historical research worker.

## New executable bridge
- src/norisk_quant/research_control_plane.py now offers lease-fenced
  private leased_research_intent(). A forged/expired/revoked token cannot
  read an experiment's stored parameters, dataset hash or source selection.
  Do not expose this method in any Terminal browser/API response.
- src/norisk_quant/canonical_research_worker.py converts a single
  approved built-in **m1-sweep M1** proposal into the existing
  NRFX_FROZEN_BATCH_V1 orchestrator contract, and verifies source, exact
  git HEAD and historical month scope before any actual CLI backtest.
- scripts/canonical_research_worker.py provides private status, operator
  explicit --resume / --pause controls and a separate --execute for **ONE**
  research job. It starts no daemon and has NO trade/broker API.
- The existing canonical research_batch_orchestrator.run_plan() owns
  execution, official Bid/Ask M1 synthetic-research scenario, accounting,
  audit_run(), trades.csv, weekly.csv, monthly.csv and batch_manifest.
  The new agent queue receives ONLY SHA256 of its already-audited batch
  manifest with reason code historical_audit_pending. It cannot claim
  independently validated OOS, profitable months, broker fill accuracy,
  trading eligibility or live approval.
- A heartbeat keeps the claim fenced while a large original Gold ZIP is
  preflighted and while the bounded canonical subprocess runs. If worker
  death causes lease expiry, a stale token cannot publish a result.
- Any source mismatch, invalid strategy mapping or failed canonical audit
  is rejected and queued work is NOT automatically retried. A human must
  inspect the protected artifacts first.

## Explicit researcher invocation — PRIVATE workstation
Prerequisites: a CLEAN pinned backtest-engine Git checkout at the exact
proposal commit, an already-registered source-manifest JSON for ONE full
historical UTC month, a source original Gold ZIP entirely outside public Git,
and an existing empty local private report directory.

Default safe status:
    python scripts/canonical_research_worker.py --queue-db PRIVATE_QUEUE.sqlite3

Explicit operator resume:
    python scripts/canonical_research_worker.py --queue-db PRIVATE_QUEUE.sqlite3 --resume

One bounded historical-only canonical simulation:
    python scripts/canonical_research_worker.py --queue-db PRIVATE_QUEUE.sqlite3 --execute --source-manifest PRIVATE_FROZEN_MONTH_SOURCE_MANIFEST.json --original-gold-zip ORIGINAL_PRIVATE_GOLD.zip --checkout CLEAN_PINNED_ENGINE_ROOT --private-output PRIVATE_LOCAL_OUTPUT_DIRECTORY

Explicit operator pause:
    python scripts/canonical_research_worker.py --queue-db PRIVATE_QUEUE.sqlite3 --pause

Never place original source quotes, private account IDs, queue files,
agent-private JSON, Oracle configuration or credentials in the PUBLIC repo.

## NON-GOALS and deliberate limits
- Nova and Forge native AQL strategy names `aql_<hash>` are BLOCKED.
  They do not have automatically verified equivalent Gold implementations.
  Only the existing audited canonical `m1-sweep` strategy is currently
  allowlisted, and only with canonical validated numeric parameters.
- One frozen closed UTC calendar month of original ZIP data, historical
  exposed only, original SHA/loaded-BIDASK hash and clean HEAD. ONE ounce
  and original all-in $0.40/oz roundtrip. No double-fee, no observed tick
  order model, no broker commission/slippage claims, no actual broker fill.
- Queue stores an artifact digest, not quantitative P/L or independent
  OOS. Outcomes from exploratory monthly research are vulnerable to
  multiple testing. No guaranteed positive month.
- This is an operator-triggered local command, not a production
  distributed job scheduler, 24/7 service, real-time Terminal plugin,
  running AI autonomous strategy factory, or Oracle deployment.
- Each unreviewed source manifest must be validated on the OWNER's
  PRIVATE original Gold ZIP. Synthetic GitHub tests prove only program
  behavior, not real market data or prospective profitability.
- This PR is stacked on B05 #11 and is DRAFT until real original-data
  reconciliation and independent security/scientific gates pass.
