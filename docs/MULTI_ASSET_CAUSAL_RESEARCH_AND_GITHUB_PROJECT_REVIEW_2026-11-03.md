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


## Grok Bot role desks and OANDA failure case

The following repositories specifically use **Grok Bot team/skills**, rather
than merely invoking an xAI Grok LLM as an analysis API:

- [galleonlabs/hypergrok-trading-desk](https://github.com/galleonlabs/hypergrok-trading-desk):
  seven agent roles, one authorized writer, ticket approval, 17 skills;
  Hyperliquid, not OANDA. MIT.
- [tsukiema/tsukiema-desk](https://github.com/tsukiema/tsukiema-desk):
  twenty specialized seats, cheap deterministic filters, fail-closed JSON,
  model budget, paper execution stub.
- [GrokDesk/grokdesk](https://github.com/GrokDesk/grokdesk):
  six desks, supervisor reallocates research budget and retires underperforming
  agents. Its simulation is not proven market edge.
- [swcstudiospace/PumpGrok](https://github.com/swcstudiospace/PumpGrok):
  ten staff roles, 35 portable skills and a rule that never signs live orders.
- [HammeredSmithy/bull-trade](https://github.com/HammeredSmithy/bull-trade):
  HyperGrok-style Webull team, not OANDA.
- [Mendurim/strikegrok-trading-desk](https://github.com/Mendurim/strikegrok-trading-desk):
  seven-role Strike Finance team; broker adapter is venue-specific.

**Highest priority FX/OANDA engineering comparator:**
[BrockStar3540/mr-scrooge-v6](https://github.com/BrockStar3540/mr-scrooge-v6)
(Apache-2.0) uses OANDA across many FX pairs, a governor promoting and
demoting setups, shadow outcomes, practice/real fills, hypothesis records and
a formal bug ledger. Its November 2 published ledger reported 1,127 all-time
closed real-money trades with a 78.2% win rate but **-$1,365.92 net P/L**.
This is an author-published snapshot, **not independently audited here**.
It illustrates the danger of using win rate, backtest P/L or simulation
outcomes as a substitute for actual net broker fills. Its reported poor
sim-to-broker agreement is exactly why No Risk FX needs a separately
reconciled execution adapter before assigning real capital. Read its
[research program](https://github.com/BrockStar3540/mr-scrooge-v6/blob/main/docs/RESEARCH_PROGRAM.md),
not just the strategy catalog. Never copy strategies/risk settings blindly.

Source catalog indexes:
[awesome-grok-bot](https://github.com/ZeroPointRepo/awesome-grok-bot),
[GitHub grok-bot topic](https://github.com/topics/grok-bot),
[awesome-open-source-trading](https://github.com/WallStreetPete/awesome-open-source-trading).
A search survey cannot prove that every repository has been discovered.
