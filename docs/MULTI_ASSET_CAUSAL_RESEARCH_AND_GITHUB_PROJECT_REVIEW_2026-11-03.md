# No Risk FX — Multi-Asset Causal Agent Research, first vertical slice

Date: 2026-11-03. Draft PR #1 / research only. NO OANDA live orders,
broker credentials in Git, historical strategy retuning or profitability claim.

## Scope shipped in this slice

| Layer | File | Executable behavior |
| --- | --- | --- |
| OANDA historical provider | \`src/norisk_quant/oanda_readonly.py\` | Bounded GET-only fxPractice M1 BID/ASK candle import; completed bars only |
| Macro/news causal contract | \`src/norisk_quant/causal_market_context.py\` | Release/first-seen timestamps, vintage tracking, high-impact calendar veto |
| Multi-robot signal lab | \`src/norisk_quant/robot_research_lab.py\` | Up to 32 frozen robots, strict lookback, spread/cooldown/news/gap filters, one intent per instrument/time, contradictory intents abstain |
| CLI | \`scripts/run_multi_asset_research.py\` | Offline signed-ish immutable JSON evidence outside checkout; optional bounded practice candle fetch |
| Contracts | \`tests/test_multi_asset_research_contract.py\` | Unit/contract and offline synthetic end-to-end assertions |

Robots are currently *deterministic hypothesis templates*, NOT trained models.
The three example families (momentum, mean reversion, policy rate differential)
cover simple research/causality semantics only. They are not evidence of edge.

These methods DO NOT run canonical XAUUSD P&L or actual OANDA fills. The old
gold-only $0.40/oz all-in accounting must not be transplanted into Forex
contracts; currency P&L, pip values, spreads, financing, account currency,
precision, leverage, bid/ask and broker order restrictions need a separate
verified execution integration. The CLI exports INTENTS, not orders or fills.

## Contract

All market candles must be completed, chronological M1 observations with
independent bid/ask OHLC. The decision becomes known at candle close; the
current candle OHLC cannot be traded at its open. Gaps cannot be interpolated.

Macro actuals require \`released_at\`, \`first_seen_at\`, \`vintage\` and \`source\`.
The current revised macro value cannot be used before its actual availability.
Announcements may only block decisions if the schedule was known by then.
News-source models (Grok/xAI or any other) must obey this boundary.

The multi-robot lab never touches the OANDA orders, account or trade endpoints;
no strategy is authorized for live trading, even in a profitable backtest.
A future dedicated paper gateway requires independent risk acceptance.

## Architecture reference study (selected GitHub projects)

- [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) (MIT): idea -> factor/model implementation -> tests -> iterative research.
- [OnePunchMonk/AgentQuant](https://github.com/OnePunchMonk/AgentQuant) (MIT): failure-aware memory and training/holdout isolation, alpha-stage.
- [OpenByteInc/QuantDinger](https://github.com/OpenByteInc/QuantDinger) (Apache-2.0 backend, separate frontend license): durable worker orchestration, lifecycle ownership, monitoring and gates.
- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (Apache-2.0): multi-agent analysts including optional Grok as model.
- [kyky2347/ALTA](https://github.com/kyky2347/ALTA) (Apache-2.0): independent reviewer, research/shadow/broker authority separation.
- [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) (MIT): agent research UX and declarative strategies.
- [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) (LGPL-3.0): deterministic event-driven execution architecture; no assumed official OANDA adapter.
- [QuantConnect/Lean](https://github.com/QuantConnect/Lean) (Apache-2.0): alternative independent event-based execution reference.
- [zostaff/grok-trading-desk](https://github.com/zostaff/grok-trading-desk): Grok strict JSON and fail-closed analyst roles, small experimental repo.
- [snikkam06/grok-trading-backend](https://github.com/snikkam06/grok-trading-backend): Grok reasoning/journal prototype, not validated Forex system.
- [nolancacheux/AI-Agent-Grok-Trading-System](https://github.com/nolancacheux/AI-Agent-Grok-Trading-System) (MIT): Grok analysis/IBKR order boundary, small experimental repo.
- [smoothAEON/Python_Backtester_FX_Oanda_Integration](https://github.com/smoothAEON/Python_Backtester_FX_Oanda_Integration) (GPL-3.0): OANDA data-contract research only; do not copy without GPL review.
- [WallStreetPete/awesome-open-source-trading](https://github.com/WallStreetPete/awesome-open-source-trading): 450+ curated source projects.

No third-party code was copied or vendored in this slice. Star counts and
upstream README marketing claims are not independent verification.

## Next acceptance gates

1. Confirm provider contract on OANDA practice with a private token and
   source-stamped BID/ASK observations; save only private evidence.
2. Add currency/contract-aware execution sandbox with separate fees and
   independent reference parity for FX and XAU.
3. Add immutable Experiment/MarketEvent/AgentDecision/Evidence contracts to
   the existing frozen job manager rather than spinning up a second scheduler.
4. Separate Grok or other LLM hypothesis agents from deterministic execution
   gates, with prompt/tool-call provenance and explicit research budget.
5. Add paper-mode reconciler and risk limits; no live adapter until explicit
   approval and real crash/restart/kill-switch drills.
6. Add true prospective out-of-sample holdout and multiple-testing penalties.
