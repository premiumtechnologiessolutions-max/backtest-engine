# Upstream source checkouts pinned — 2026-11-04

**This repository now contains Git submodule references to the original upstream
source trees, not copied/vendored code bytes.** After a recursive Git checkout,
the complete upstream source trees appear inside `vendor/upstream/`. This
avoids duplicating hundreds of megabytes in the No Risk FX Git history.
It does NOT mean the engines are installed, sandboxed, integrated, or passing
end-to-end tests with No Risk FX. No upstream code is executed automatically.

| Source directory | Upstream | Frozen commit | License reported by upstream |
| --- | --- | --- | --- |
| `vendor/upstream/lean` | https://github.com/QuantConnect/Lean | `9ecfed98339c27849a2a708edc03455caf151e91` | Apache-2.0 |
| `vendor/upstream/nautilus_trader` | https://github.com/nautechsystems/nautilus_trader | `6c843bc7f9f72941eeddb22df502b520c97a8987` | LGPL-3.0 |
| `vendor/upstream/rd_agent` | https://github.com/microsoft/RD-Agent | `484776c211e4fbbeef03e0ec00d6bbee7362a4f4` | MIT |
| `vendor/upstream/tradingagents` | https://github.com/TauricResearch/TradingAgents | `9fa1196fffbcfd9de5146d2dd2869df84ab99838` | Apache-2.0 |
| `vendor/upstream/finrl` | https://github.com/AI4Finance-Foundation/FinRL | `7e98df461cbc7772f16a545a2f13b521e5d0b8f4` | MIT |

For a checkout where the original code should be available locally:

```bash
git submodule update --init --recursive
git submodule status
```

Submodule status must show the pinned commit hash without an initial `+`
(marking mismatch). Preserve upstream LICENSE, notices, trademark rules, and
third-party dependencies. Do not expose private data or credentials to an
upstream executable. The huge LEAN/Nautilus repositories are not installed
by default in CI and require distinct operating environments. No trading.

**Not yet integrated**: OpenBB (the earlier repository path redirected; canonical
source and component license still need verification), NoRiskFX Terminal,
Tradli-style features, real provider-specific data adapters, execution
supervisor and independent result acceptance. The earlier source interchange
is a metadata interface and cannot substitute for executing tested integrations.

A failed submodule fetch is not proof that the research engine works; it is a
checkout failure. These pinned source references are **not** evidence of
strategies or trading edge.
