# Quant mission-control offline UI (engineering only)

Open `web/quant-control/index.html` directly in a modern desktop browser.
Use **Load local status JSON** to select the small JSON object produced by
`python -m scripts.quant_construction_snapshot --design /private/frozen_design.json`.

The page has three functional sections: Architecture, Integrations, Missing
gates. It renders strategy/shard/DAG counts, expected resource ceilings and
read-only SQLite health. Every provider/AI reviewer is marked PLANNED /
UNVERIFIED. The status remains NOT READY FOR MARKET RUNS regardless of
rendered counts. This is an honest construction dashboard, not proof of a
working integrated market execution platform.

Security: self-contained HTML, no external fonts/libs/images or network
calls. CSP blocks connections; local JSON input is 2 MB maximum and text is
inserted by textContent, not HTML. No private quote data, credentials, result
files or browser telemetry are exported by this UI. It does not persist a
snapshot or launch any backend. It also does not establish cryptographic
authenticity of the uploaded JSON; the CLI must validate the frozen design
before exporting the dashboard feed.

Readiness work remains: actual provider runners, independent acceptance
pipeline, cross-platform supervised workers, authenticated roles, operations
and backup/recovery, full UI-to-backend integration, and owner-approved
research only after engineering completion.
