# No Risk FX Quant Research Terminal — acceptance and release gates

Updated 2026-10-27. The product is **not** ready for live trading or unrestricted execution.

## Implemented
- Default command: `python scripts/research_terminal.py` (from repository root) generates `reports/research_terminal.html`.
- Responsive navy/gold local HTML, no external scripts, broker APIs, telemetry or external financial credentials.
- Three functional sections: Overview, Strategy Lab, Verification.
- Source-of-truth counts from the existing `audit_strategy_factory_registry` fail-closed validator, then `dashboard_model`.
- Maximum positive design-month coverage display (0–24), carefully labeled as **historically exposed** research, not expected monthly returns.
- Interactive family catalogue: search, reported-status filter, sortable specs / positive-month coverage / ID, comparison of up to three families.
- Linked evidence reports only when supplied in the registry and restricted to repository-local docs/ or research/ paths; content HTML-escaped.
- Explicit absence of true per-run equity curves, trade P/L, robust broker execution, independent prospective OOS, and live-order capabilities.
- Standalone renderer source in `scripts/research_terminal_ui.py`, regression tests in `tests/test_research_terminal_ui.py`.

## Run and test

```sh
python -m pip install -e '.[dev]'
python -m pytest -q tests/test_research_terminal.py tests/test_research_terminal_ui.py
python scripts/audit_strategy_factory_registry.py
python scripts/research_terminal.py
```

Open the output file in a browser. This is a read-only generator; its source is the then-current registry snapshot, so regenerate after research changes. It does **not** live-refresh or schedule backtests.

## Acceptance checklist before saying 'complete'
1. **Source/CI:** exact-HEAD full test suite passing; registry arithmetic and original private Gold source provenance checked; no raw price upload to this public repo.
2. **Model/results:** each displayed performance metric has immutable experiment ID, parameter set, source SHA, source code commit, assumptions and independently replayed trade/equity ledger. Mark absent metrics as N/A.
3. **Validation:** frozen train/embargo/evaluation definitions, separate truly unseen prospective OOS, realistic cost/tick stress and capacity-aware portfolio fills. A historical positive-month maximum does not prove profitability.
4. **Production UI:** desktop/mobile accessibility testing, bilingual Arabic/English RTL UX, brand-logo asset added with owner authorization, end-to-end state/error handling and a non-demo production deployment.
5. **Job orchestration:** authenticated and authorized queued backtests, constrained resource limits, resumable state, isolated private-data storage, audit logs, safe cancel/retry and explicit permission boundaries.
6. **Operations:** reproducible deploy and rollback docs, configuration/secrets inventory, health checks, failure recovery, smoke test and security review.
7. **Financial use:** broker/paper or live integration requires separate, explicitly authorized scope and risk limits; do not wire automatic live trading as a side effect of the dashboard.

## Verification as of initial UI commit
A local independently constructed UI fixture was used to smoke-test Chromium desktop/mobile rendering, catalog search and one-family selection, and Python renderer smoke checks (4 local checks). These checks use **illustrative family rows**. They are **not** a full current-HEAD GitHub CI run and **not** a replay of the private original Gold data. At the time of the note, GitHub CI for these commits had not reported a run. Keep PR #1 Draft/unmerged.
