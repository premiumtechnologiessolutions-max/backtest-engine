# ADR 007 — Controlled External Quant-Code Adoption & Formula Gateway

Status: first integration seam implemented; vendor runtimes NOT yet imported.
Date: 2026-11-03. Draft PR #1 (public repository).

## Why not copy five GitHub projects into one source tree?

RD-Agent, OpenEvolve, AgonAlpha, Mr. Scrooge and QuantDinger operate with
different data conventions, experiment engines, file/state stores, and runtime
requirements. Running their full stacks side by side would reintroduce the
duplication we are removing. Upstream passing tests establish behavior only in
their own version/environment; they do NOT certify our instrument fees,
XAUUSD M1 limits, causal macro context, true OANDA fills or profitability.

**No license clearance burden placed on the owner for the permissively
licensed components listed here**; when code is copied, preserve upstream
license + notices + version provenance. Clear third-party copyright/model/
data terms before copying anything without an explicit reuse license.

## Upstream source snapshot pins, not installed dependencies

| Component | Pinned external commit | License reported on GitHub | Intended integration |
| --- | --- | --- | --- |
| [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent) | \`484776c211e4fbbeef03e0ec00d6bbee7362a4f4\` | MIT | Proposal agent (never scorer) |
| [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve) | \`73448d715968b3578d8458b16295e827edd2b6bf\` | Apache-2.0 | Bounded evolutionary formula search |
| [AgonAlpha](https://github.com/AutoResearch-Factory/AgonAlpha) | \`334f808df72d3da1ff78561d67700a7cf225af15\` | MIT | MCTS selection with independently verified fitness only |
| [Mr. Scrooge V6](https://github.com/BrockStar3540/mr-scrooge-v6) | \`bed8d097dabb3c70e810523063eff0aee6645521\` | Apache-2.0 | OANDA account/broker transaction reconciliation pattern |
| [QuantDinger](https://github.com/OpenByteInc/QuantDinger) | \`e75f0cfa9cd47de9259844fefbf20c2fa1464d45\` | Apache-2.0 **repository**; audit per subproject/asset before copying | Worker/UI architecture |

These commits anchor a *source review*, not an independent code security audit
or a claim that any upstream project was executed inside NRFX. No upstream
source files or binaries have been vendored in this commit.

## First implemented component

\`scripts/import_external_formula_proposals.py\` is the strict,
dependency-free gateway for **off-platform** RD-Agent/OpenEvolve/AgonAlpha
formula proposals. It accepts JSON with exactly these keys:

\`\`\`json
{
  "schema": "NRFX_EXTERNAL_FORMULA_INTAKE_V1",
  "generator": "openevolve",
  "source_commit": "73448d715968b3578d8458b16295e827edd2b6bf",
  "proposals": [
    {
      "lookback": 20, "feature_a": 0, "feature_b": 2, "feature_c": 1,
      "operator_ab": 0, "operator_c": 0, "reverse": 0,
      "threshold": 1.0, "stop_usd": 8.0, "reward_risk": 1.5,
      "cooldown": 10
    }
  ]
}
\`\`\`

Run offline:
\`python -m scripts.import_external_formula_proposals --input /absolute/proposals.json --out /absolute/private/import_001\`

This publishes the canonical **same Formula JSON** consumed by the existing
\`norisk backtest --strategy arithmetic --timeframe M1 --formula-json ...\`.
There is NO direct import of provider code, no Python \`eval\`, no touching
original Gold ZIP, no execution, no P/L, no scoring or live orders. It
rejects untrusted extra fields such as \`code\`, \`fitness\`, \`orders\`, or
\`holdout_result\`; malformed records, repeated formulas and mutated
published evidence fail closed. Private output must be outside Git checkout.

The exact GitHub upstream SHA is **caller asserted** and allowlisted; the
gateway does not authenticate the origin/identity of the external agent.
An independently reviewed provider runner and artifact signature/attestation
are required before source attribution can be considered verified.

This integration deliberately leaves the verified XAU evaluation loop
authoritative. Its historical $0.40/oz ALL-IN fee must not be generalized to
EUR_USD and other forex pairs. No independent OOS edge is proven.

## Further integrations, each gated

1. Run a separate isolated OpenEvolve process with a **restricted formula AST**
   and no network, credentials, original quote archive, holdout or arbitrary
   code access; emit only the JSON above; benchmark identical budget versus
   current generator. Do not run a generic coding agent inside the engine.
2. Add MCTS from AgonAlpha only with an **attested score receipt** directly
   from the existing frozen referee, never arbitrary CLI \`--score\`.
3. Introduce a broker transaction *read-only* practice reconciler using
   OANDA transaction IDs and side-specific quote/units/account currency.
4. Integrate a single canonical job lifecycle before adopting QuantDinger's
   queue, UI or another supervisor.
5. Reevaluate post-cost OOS performance, data rights, license notices and
   host resource usage before a second provider is accepted.

Repository remains PUBLIC and PR #1 remains Draft until engineering review.
