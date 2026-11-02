# No Risk FX — host-resident autonomous training, 2026-11-02

The **unattended research service** supervises the existing research director
on an independently running machine, not inside a ChatGPT conversation.
Committing this code DOES NOT deploy or install it on the user's computer.

Operation: SHA-pinned private Gold ZIP -> matched-guided formula hypotheses ->
canonical reference and fast annual executions -> full accounting and lineage
verification -> next-generation feedback -> local read-only dashboard.

A systemd unit template is provided at
\`deploy/norisk-quant-research.service\`; the private configuration can be
based on \`deploy/research-agent.example.json\`. Windows launcher template:
\`deploy/Start-NoRiskFXResearch.ps1\`. The host administrator must install
these on an actual machine with locally held private data and a configured
Python environment. No GitHub-hosted job should access or upload the raw ZIP.

Status: owner-only \`unattended_research_health.json\` (heartbeat and
last lifecycle state) and \`autonomous_research_status.json\` (audited
generation progress). The service retries bounded resource/time pauses,
but stops for corrupted, missing, stale or contradictory execution evidence.
On reboot, an installed OS service manager can relaunch it.

Verified local acceptance: the SHA-pinned original ZIP was used for an
existing three-generation historical 2012/2013 training campaign. The new
service re-ran the independent cache audits, supervised the canonical director,
and reported \`TRAINING_CAP_REACHED_NOT_OOS\` with three verified generations.
This was NOT a 24/7 host test, a 200-generation run, or untouched OOS.

Scope limits: **only the arithmetic family** is adaptive so far (six causal
features and parameter mutations). A complete autonomous quant platform still
needs cross-family algorithm design, persistent knowledge across campaigns,
true forward evaluation, multiple-testing corrections, resource benchmark
at scale, operator UI/alerts, and actual boot-restart acceptance on an
always-on host. The current campaign cap is 200 generations, after which
the service safely stops instead of pretending indefinite learning.
Neither this platform nor its tests certify monthly profits or live trading.

Repo visibility is currently PUBLIC. Keep Gold ZIP, market ledgers and
private research output outside the repository. PR stays Draft until
release evidence is complete.
