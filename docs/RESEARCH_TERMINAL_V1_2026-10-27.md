# No Risk FX — Quant Research Terminal (read-only v1)

This is a working research-registry dashboard generator, not a trading robot or proof of profitable algorithms.

## Run
From the repository root with the Python project dependencies installed:

    python scripts/research_terminal.py

Open reports/research_terminal.html in any browser. For a custom input and output:

    python scripts/research_terminal.py --registry research/strategy_factory_registry.json --out reports/research_terminal.html

## Display
- Registry timestamp and exposed-design research status.
- Audited totals: parameter specifications, active annual replays, research families, passing 24/24 design-month specs.
- Filterable family table: hypothesis, parameter counts, filled-trade annual replays, best positive-month count, reported verification status, links to supporting notes.
- Explicit historic-data/execution cautions; no fictional profitability.

The tool calls the existing registry arithmetic auditor before writing the output. Inconsistent counts cause failure rather than misleading output. Registry text is HTML-escaped, and evidence links must use repository-local docs/ or research/ paths. The offline HTML has no CDNs, analytics, API access, raw quotes or broker credentials.

Run focused tests:

    python -m pytest -q tests/test_research_terminal.py

## Limits
The registry contains strongly correlated parameter choices tested against historically exposed design years, not independently certified successful strategies. Full qualification still needs exact-source replay, immutable code/data fingerprints, prospective untouched out-of-sample evaluation, execution parity and cost stress.

This first increment intentionally does not start backtests, retrieve live market data, send orders, control MT5, ingest the private Gold ZIP or compute hypothetical metrics. It is a read-only view over existing auditable metadata, not yet an automated all-in-one Quant Lab.

Keep PR #1 as Draft/unmerged pending full-head CI, source checks and independent evidence.


## Optional verified local Research Jobs view (2026-10-28)

Use `python scripts/research_terminal.py --include-local-jobs` to opt in to
displaying local queued job metadata in the generated offline HTML. Without the
flag, the HTML **does not embed local job fingerprints**. The queue reader
`scripts.research_job_queue.list_jobs` validates each entry, ownership,
permissions, schema and SHA256; any unsafe/tampered record aborts the export
before writing HTML. At most 500 verified jobs may be rendered.

The new Research Jobs tab shows frozen request fingerprints, families,
evaluation windows and source-commit prefixes. **QUEUED_NOT_EXECUTED** is not
running, completed, or preflight-approved. All P/L, worst-month and floating-DD
fields are N/A. This is static local metadata, not a worker, scheduling service,
resume system, OOS result, broker interface or authorization to execute.
Avoid sharing generated HTML containing opt-in local job fingerprints.


## Verified immutable month plans in the offline terminal (2026-10-28)

Only after a frozen request has been queued and its immutable monthly plan
persisted on the **exact clean frozen checkout**, an operator may opt in to
viewing month-slot metadata:

```bash
python scripts/research_terminal.py --include-local-jobs --include-local-month-plans
```

The two opt-ins are required together. Every queued request must have a
persisted plan: missing, tampered, stale, unsafe or mismatched snapshots abort
the entire HTML export. At most 20 requests × 120 months are displayed.
The UI re-verifies snapshots via `verify_plan`, including exact-checkout
preflight, and renders immutable UTC month identifiers and abbreviated
fingerprints. The HTML contains local request metadata and should not be
shared publicly.

**All month slots are PLANNED / NOT EXECUTED.** Source verification, monthly
net P/L and floating M1 drawdown display N/A. This is not a worker, checkpoint,
resume mechanism, market data validation, future OOS proof or a live connection.
The published registry is not modified by planning-only changes.
