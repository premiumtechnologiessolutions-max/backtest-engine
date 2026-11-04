# External upstream code review and selection log — 2026-11-04

## Scope and limitations

This is a **targeted source-level audit** of 13 inspected upstream files at
immutable Git revisions, not a line-by-line audit of every file in six huge
repositories. Source contents were fetched directly at the commit hashes
below. The upstream implementations remain their authors' code, accessible
through pinned submodules. The new Python stream merger is **original
implementation based on reviewing** the replay interface/semantics; it is
not a verbatim transplant of LGPL Rust code.

The repo's own existing modules were compared:
`src/norisk_quant/data.py` performs strict original M1 BID/ASK validation;
`causal_market_context.py` already validates release and first-seen clocks;
`research_evolution.py` and `research_candidate_memory.py` already support
bounded training-only evolution; and the durable SQLite state does not support
external execution or accepted result transitions.

## Verified upstream file selection

| Project + pinned source | Inspected file(s) | Relevant code and decision | Integration status |
| --- | --- | --- | --- |
| QuantConnect LEAN `9ecfed98339c27849a2a708edc03455caf151e91` | `Engine/DataFeeds/SubscriptionSynchronizer.cs`; `Engine/Results/BacktestingResultHandler.cs` | Event frontier synchronization; progress/result handler separation. C# and framework-specific; retain original upstream source for separate controlled runner rather than copying into Python. | Source linked; executor NOT wired |
| NautilusTrader `6c843bc7f9f72941eeddb22df502b520c97a8987` | `crates/data/src/replay/iterator.rs`; `crates/backtest/src/data_iterator.rs`; `crates/event_store/src/manifest.rs` | Named streams, deterministic equal-time ordering, monotonic source bounds, run manifest states including crash recovery/quarantine. Use original source through submodule; implement small independent Python research-only causal merger now. | Python causal merger + tests added; Rust engine NOT wired |
| Microsoft RD-Agent `484776c211e4fbbeef03e0ec00d6bbee7362a4f4` | `rdagent/core/evolving_framework.py`; `rdagent/core/evaluation.py` | Evolution steps and feedback history useful; existing bounded local evolution overlaps. **Important:** base `Feedback.__bool__` returns True, so never treat default feedback as trade acceptance. | Architecture assessed, not executed or copied |
| TradingAgents `9fa1196fffbcfd9de5146d2dd2869df84ab99838` | `tradingagents/graph/checkpointer.py`; `tradingagents/graph/trading_graph.py` | Signature-sensitive deterministic graph resume and per-ticker SQLite checkpoints. Useful for AI analysis state, but segregate from research result acceptance and broker execution. | Source linked; checkpoint runtime NOT wired |
| FinRL `7e98df461cbc7772f16a545a2f13b521e5d0b8f4` | `finrl/meta/data_processor.py` | Data-vendor facade and RL dataset interface; current `df_to_array` silently replaces nonfinite features with zero. **Reject that preprocessing behavior** for provenance-critical market data. Use only isolated future RL tests. | Source linked; RL runner NOT wired |
| OpenBB/OpenBQ `2a392e890f6eb1f0f4e3a71742720af8f056333a` | `openbb_platform/core/openbb_core/provider/registry.py`; `openbb_platform/core/openbb_core/provider/query_executor.py`; root `LICENSE` | Provider registration/credential filtering. Historical macro vintages still need `released_at`, `first_seen_at`, immutable snapshot and independent source checks. The new canonical organization is `openbq-org`. | Source linked; provider API NOT installed or run |

Upstream source code can be fetched from submodule checkouts via
`git submodule update --init --recursive`, but this is a potentially large
download (especially LEAN, Nautilus and OpenBB). **Do not load their entire
dependency stacks into our standard CI environment.** Maintain separate
isolated toolchains, monitor their own licenses and dependency supply chain.

## What was actually implemented in this change

`src/norisk_quant/causal_stream_merge.py` is a bounded research-only adapter
that keeps source digests, event timestamps, availability/first-known
timestamps, strictly monotonic per-source sequences, explicit equal-time
precedence and deterministic replay. It refuses nonfinite values, boolean
timestamps, source drift and out-of-order feeds. It is intended for research
alignment of M1 market data with macro/news streams, without ever allowing
a late-arriving value to leak into past decisions. It does not yet connect to
the backtest CLI or host supervisor. Tests use synthetic data only.

## Next acceptance gates

1. Integration test with frozen original data and distinct macro vintages,
   ensuring no future release leaks into M1 decision time.
2. Isolated OpenBB read-only source adapter, frozen exact provider version,
   rate limits, cache manifest and first-seen/release clocks.
3. Isolated and reproducible LEAN/Nautilus reference comparison without
   assuming different fill semantics are interchangeable.
4. TradingAgents graph checkpoint storage separated from SQLite research-job
   lease authority; RD-Agent proposal loop restricted to training evidence.
5. FinRL evaluation environment with our fill/cost, split and quote integrity
   checks, never silently imputing broken market data.
6. Independent receipt acceptance; original full 13-field ledger parity;
   restored host supervisor and backup/recovery tests; unified UI.
7. Review other previously discussed repositories only after exact canonical
   source and code version are established (NoRiskFX Terminal, Tradli-style
   project, additional data vendors).

Do not claim the provider submodules, metadata bridge, or synthetic causal
merge establish an alpha, live-trading readiness, or complete code audit.
