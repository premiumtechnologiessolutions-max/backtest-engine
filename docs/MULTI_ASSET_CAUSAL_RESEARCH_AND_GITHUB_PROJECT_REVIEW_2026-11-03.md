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


## Phase II: Source-inspected architecture due diligence (2026-11-03)

**Method:** verified public GitHub metadata, repository directory trees, relevant
Python implementation files, official OANDA/FRED documentation and upstream
README claims. This is architectural investigation, NOT a security audit,
quantitative re-run, upstream integration, or trading-performance verification.
Star counts are omitted as an engineering acceptance criterion.

### 1. Critical shortlist — fit, actual implementation and no-go conditions

| Project and source | Source-inspected capability | License / caveat | NRFX use | Action |
| --- | --- | --- | --- | --- |
| [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent) | R&D hypothesis/proposal + developer/evaluator loop; quant factor/model co-optimization | MIT; high LLM cost and not an FX/Gold execution model | **Research brain pattern**, existing deterministic runner remains authority | ADAPT interface, not entire stack |
| [QuantaAlpha](https://github.com/QuantaAlpha/QuantaAlpha), [loop.py](https://github.com/QuantaAlpha/QuantaAlpha/blob/main/quantaalpha/pipeline/loop.py), [user guide](https://github.com/QuantaAlpha/QuantaAlpha/blob/main/docs/user_guide.md) | Actual factor_propose -> construct -> calculate -> backtest -> feedback loop; planning/mutation trajectories and factors library | README and pyproject **claim MIT**, but no root LICENSE file or GitHub-detected license was visible; model/research figures unverified for our market | Expand beyond fixed arithmetic grammar | **DESIGN STUDY**, code reuse blocked pending license clearance |
| [AlphaGen](https://github.com/ICT-FinD-Lab/alphagen) | Formulaic alpha language + RL generator, Qlib integration and experimental trading | Root LICENSE absent in reviewed tree; stock cross-section, RL compute burden | Symbolic formula discovery & grammar constraints | DESIGN STUDY only |
| [Qlib](https://github.com/microsoft/qlib), [recorder](https://github.com/microsoft/qlib/blob/main/qlib/workflow/__init__.py) | \`qlib/workflow\` records experiments and model/data artifacts; factors, backtest, ML | MIT; equities-first | Single immutable experiment/evidence lineage; avoid adding second ledger | ADAPT contract, not vendor large dependency yet |
| [Aurum](https://github.com/zero-was-here/tradingbot), [macro](https://github.com/zero-was-here/tradingbot/blob/main/aurum/data/macro.py), [walkforward](https://github.com/zero-was-here/tradingbot/blob/main/aurum/research/walkforward.py) | Gold canonical bars and \`available_at\`, source integrity, purge/embargo, holdout | MIT; **estimated publication lag != ALFRED vintage or exact release-time feed**; author claims not independently proven | Point-in-time bar/macro contracts and leakage negative controls | BUILD CROSS-CHECK TESTS |
| [duka-data](https://github.com/saleem-latif/duka-data), [integrity](https://github.com/saleem-latif/duka-data/blob/main/check_integrity.py) | FX/metal tick BA download, gap/coverage/spread checks, repair ledger | MIT source; **third-party Dukascopy data terms**; small repo, independently validate price scales | Independent quote-feed comparator against OANDA/XAU original | DATA PILOT only; no raw uploads |
| [purgedcv](https://github.com/landtml/purgedcv), [proof](https://github.com/landtml/purgedcv/blob/main/PROOF.md) | CPCV/purged fold splits with embargo and formal stated label-window proof | MIT; proof only of split boundaries, not causal feature code or profitability | Supplement existing frozen walk-forward validation | EVALUATE WITH ADVERSARIAL TESTS |
| [Optuna](https://github.com/optuna/optuna) | Efficient multi-objective parameter search and persistence | MIT; optimizer can overfit research period spectacularly | Budgeted search of **training-only** predeclared parameter spaces | PILOT with paired random/grid baseline |
| [fredapi](https://github.com/mortada/fredapi), [source](https://github.com/mortada/fredapi/blob/master/fredapi/fred.py) | \`get_series_as_of_date\`, \`get_series_first_release\`, \`get_series_all_releases\` | Apache-2.0; **ALFRED vintage dates by themselves do not prove exact intraday publishing time** | Causal policy rate/inflation/GDP historical series | DATA PILOT plus independent release time |
| [OANDA official SDK](https://github.com/oanda/v20-python), [OpenAPI schema](https://github.com/oanda/v20-openapi) | REST v20 contract; GET candles, account pricing/trade endpoints segregated | MIT client code, SDK last pushed 2021; pricing stream is throttled/partial (not tick truth) | Practice feed and future execution adapter as separate processes | KEEP read-only, no live adapter authorization |
| [FinRL-Meta](https://github.com/AI4Finance-Foundation/FinRL-Meta) | Market environments decoupled from agent/learning algorithm; RL benchmarking | MIT, stock/crypto-centric; simulator mismatch for FX | Eventually training agents via calibrated FX/XAU gym environment | DEFER until execution parity |
| [Prefect](https://github.com/PrefectHQ/prefect) | Durable orchestration, task retry, state and worker supervision | Apache-2.0; additional operational/database dependency | Future job scheduler when existing supervisor proves insufficient | BENCHMARK, don't install yet |
| [yebof/quant-agent](https://github.com/yebof/quant-agent) | Special-purpose agents, Pydantic contracts, protected execution invariants; audit/rollback-oriented prompt evolution | MIT; small self-reported equities project, no independent P/L verification | Restrict agent output to typed intent and protect risk code from prompt edits | ADAPT architectural constraints |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | Deterministic event-driven high-performance execution concepts | LGPL-3.0; Rust/C++ bridge, adapter coverage and obligations need review | Independent execution/event model reference | DO NOT replace current engine blindly |
| [LEAN](https://github.com/QuantConnect/Lean) | Established event-driven benchmark and broker abstractions | Apache-2.0; C# integration cost; may not reproduce our all-in 0.40 XAU assumptions | External parity benchmark for a small frozen case | LATER spike, not wholesale migration |
| [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | Financial NLP adaptation, news extraction, finetuning examples | MIT **code**; separately verify each model's weights and data rights | Time-stamped news features; not a trading signal oracle | DESIGN PILOT |
| [FinBERT](https://github.com/ProsusAI/finBERT), [model card](https://huggingface.co/ProsusAI/finbert) | English financial news sentiment | Apache-2.0 **code**; actual model weights are **CC BY-NC-SA 4.0** (non-commercial) | Do **not** use weights in commercial No Risk FX without separate permission | **BLOCK** |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Specialized macro/news/technical debate roles | Apache-2.0; decisions are language-model opinions, not causal backtest edge | Role design and output contracts only | REFERENCE |
| [Ray](https://github.com/ray-project/ray) | Distributed execution and resource scheduling | Apache-2.0; large overhead for a low-cost single host | Thousands of jobs across future cluster | DEFER |
| [DuckDB](https://github.com/duckdb/duckdb) | Analytics over local Parquet and SQL joins | MIT; separate analytical index not independent immutable truth | Optional read-only research query layer after canonical evidence store | EVALUATE |

**Important:** QuantaAlpha's README performance and paper's returns are
author-provided on mainly stock-universe data; they are NOT independently
verified evidence for FX/XAUUSD. Similarly the self-reported formal proof for
purgedcv, 874 tests in quant-agent or performance figures for other projects
are not certification until NRFX adversarially replays the relevant property.
Do not copy or vendor code with unclear license, even when a README badge
claims permissive licensing. FinBERT **model weights** have a distinct
noncommercial license from the code.

### 2. External official constraints verified

- OANDA [candles OpenAPI](https://github.com/oanda/v20-openapi/blob/master/yaml/separate/v20_instrument.yaml):
  bid+ask \`price=BA\` and completed M1 candles; bar OPEN timestamp is not
  decision availability. Keep our adapter bounded and read-only.
- OANDA [account price stream](https://developer.oanda.com/rest-live-v20/pricing-ep/):
  at most 4 prices/second/instrument and not all broker ticks. Do not claim
  historical M1 or stream replay is tick-by-tick executable broker truth.
- [FRED real-time parameters](https://fred.stlouisfed.org/docs/api/fred/series_observations.html):
  \`realtime_start\`, \`realtime_end\`, \`vintage_dates\` and observation
  \`realtime_start\` represent data vintage. Default FRED mode shows what
  is known **today**, not what was known historically.
- [BLS release scheduling](https://www.bls.gov/about-bls/dissemination.htm):
  US principal indicators normally publish at 08:30 US Eastern, subject to
  scheduling and extraordinary delays. Never **assume** that time for an
  unverified historical event; store the actual source-specific timestamp
  and schedule-announced time with timezone/DST provenance.
- Historical news content rights/availability are distinct from an API code
  license. Retrieval after publication must not be falsely backdated to the
  headline time; preserve \`first_seen_at\` and revision lineage.

### 3. Recommend ONE canonical research process, not 20 new services

The existing \`research_batch_orchestrator\`, \`research_autonomous_director\`,
\`research_unattended_service\` and \`quantlab_desktop\` are *separate*
controllers today. Consolidation is a higher priority than adding more
provider/strategy scripts.

Desired strict states:
\`PROPOSED\` -> \`FROZEN\` -> \`QUEUED\` -> \`RUNNING\` ->
\`AUDIT_PENDING\` -> (\`REJECTED\` | \`TRAINING_ACCEPTED_NOT_OOS\`).
Only separately registered **future** evaluations can produce
\`INDEPENDENT_HOLDOUT_EVALUATED\`; even a statistically promising outcome
must remain \`NOT_LIVE_AUTHORIZED\` until independent paper-fill/risk review.

Canonical experimental envelope must include:
\`strategy_family\`, \`hypothesis_id\`, \`model_or_formula_sha\`, \`engine_commit\`,
\`source_sha256\`, \`data_provider\`, \`instrument\`, \`quote_side\`,
\`instrument_units\`, \`decision_asof_utc\`, \`market_available_at\`,
\`economic_released_at\`, \`economic_first_seen_at\`, \`economic_vintage\`,
\`train_window\`, \`purge_embargo\`, \`holdout_window\`,
\`fee_and_execution_contract\`, \`search_budget\`, \`worker_attempt\`,
\`monthly_weekly_equity_evidence\`, \`acceptance_decision\`.
Never infer omitted timestamps from current revised macro values.

Trade/cost contracts must be **instrument-specific**: preserve the XAUUSD
historical frozen $0.40/oz **all-in** assumption for its existing tests;
Forex pairs need quote/base/account currency conversions, contract units,
spread, overnight financing, order minimums and a separately validated
cost model. Do not reuse XAU fee semantics for EUR_USD.

An LLM (Grok, Qwen or otherwise) may create an untrusted **hypothesis plan**
or formula AST; it must never mutate audited risk logic, run unrestricted
generated code, look at independent holdout outputs during search, or call
an order endpoint. Deterministic validators and broker gateways are separate
and non-overridable by prompts.

### 4. Adoption experiments: accept by measured evidence, not GitHub fame

| Spike | Budget/scope | Must PASS | Fails if |
| --- | --- | --- | --- |
| Data cross-check | EUR_USD and XAU_USD one bounded week, OANDA practice versus licensed Dukascopy | timestamp/unit mapping, gaps, BID/ASK/spread stats, source SHA; differences documented | invents missing ticks or calls broker order endpoints |
| Macro vintage test | 3 historical events each with first observed, vintage and UTC release time; include retrospective revisions | model at T cannot see T+1 vintage; DST, delayed-release and calendar-change negative controls | date-only series treated as intraday exact |
| Formula planning | Existing grammar vs optional QuantaAlpha **inspired** prompt proposals | identical frozen budget; AST constrained; duplicate suppression; lineage SHA | arbitrary code, license contamination, holdout peek |
| Search efficiency | Optuna vs grid/random on previously exposed training, same walltime/seed/cost contract | immutable experiment receipts and repeatable selection | objective accesses future holdout; cherry-picking |
| Evaluation integrity | CPCV and fixed walk-forward using true label end/holding horizon, embargo and code-level causality tests | adversarial leak tests pass; untouched future evaluation still sealed | “OOS” reused during iterative model selection |
| Agent safety | Conflicting models in same symbol/time and missing/stale macro/data | deterministic ABSTAIN, no duplicated portfolio exposure; no order endpoint reachable | LLM bypasses veto/risk or missing data => BUY |
| Operations | real host failover/kill/restart, forced disk budget/power cycle | resumes exactly once, truthful health, durable evidence, no public quotes | green heartbeat without audited result |
| FX execution | side-specific BID/ASK, margin/units/currency conversion | reference-vs-fast parity, independent tick/paper reconciliation | uses XAU .40/oz on forex, fabricates fills |

**Recommended next implementation order (not yet executed by this document):**
(1) canonical Experiment/MarketEvent/RobotDecision/Evidence schemas and
one job-state machine; (2) observed BID/ASK and macro-vintage point-in-time
data pilot; (3) one deterministic multi-family research runner; (4) scoped
Optuna/LLM proposal adapter isolated to training; (5) paper-only broker
reconciliation; (6) prospective locked validation; (7) operating host proof.
Avoid adopting Prefect, Ray, LangGraph, or RL frameworks before establishing
a single canonical process and measuring CPU/RAM overhead.
