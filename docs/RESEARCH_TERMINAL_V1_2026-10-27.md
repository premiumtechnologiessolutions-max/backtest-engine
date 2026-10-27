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
