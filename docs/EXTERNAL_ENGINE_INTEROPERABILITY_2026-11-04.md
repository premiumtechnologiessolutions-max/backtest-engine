# External engine interoperability boundary (2026-11-04)

This commit introduces an **original**, standard-library-only JSON envelope in
`src/norisk_quant/external_research_bridge.py`. It does **not** import or
vendor third-party code and does not yet launch any external engine.

## Provider inventory / integration disposition

| Upstream | Function to evaluate | Status in this change |
| --- | --- | --- |
| QuantConnect LEAN (Apache-2.0) | Event-driven reference backtest, lean data adapter | Contract identifier only |
| NautilusTrader (LGPL) | Event-driven fills and market simulation | Contract identifier only; review linking obligations before distributing |
| OpenBB | Research data connectors | Contract identifier only; check current component licensing and credentials |
| Microsoft RD-Agent (MIT) | Hypothesis and experiment iteration | Contract identifier only |
| TradingAgents | Multi-agent analysis | Contract identifier only; verify exact repository/license |
| FinRL | RL experiments | Contract identifier only; verify exact repository/license |
| NoRiskFX Terminal | Owned UI integration | Separate architecture assessment pending |

The bridge establishes a provider-independent, content-addressed boundary:
engine ID, original data digest, code digest, frozen spec digest, and immutable
request fingerprint. External outputs must bind to that request and an actual
artifact digest. **Receipt verification is NOT research acceptance**; original
quote provenance, execution parity, fee reconciliation and independent audit
remain mandatory before any result can enter the accepted registry.

## Security and limits

No trading, execution, API calls, shell commands or provider credentials are
accepted in the envelope. There is no broker authority or live-trading setting.
All provider results remain `completed_unverified` or `failed`. The module
does not by itself offer adapters for provider-specific market formats, process
supervision, sandboxing or external code integration. Those are separate tested
deliverables. Never copy entire upstream repos without dependency, version,
license and risk review. Raw Gold ZIP stays off public GitHub.
