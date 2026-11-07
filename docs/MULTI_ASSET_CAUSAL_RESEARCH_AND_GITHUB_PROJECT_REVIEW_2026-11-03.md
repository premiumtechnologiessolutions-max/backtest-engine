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


## Phase III: Deep source review and engineering adoption decisions (2026-11-03, late session)

Scope: **read-only GitHub/API/source inspection**. No external packages were
installed, no third-party code copied, no private quote data uploaded, no API
credentials accessed, and no live or practice orders sent. This inventory is
not a security audit, independent quant proof, or a claim that all possible
GitHub projects have been found.

### Newly vetted candidates and concrete files inspected

| Candidate | Exact source inspected / evidence | Applicable pattern | Decision and blocker |
| --- | --- | --- | --- |
| [AutoResearch-Factory/AgonAlpha](https://github.com/AutoResearch-Factory/AgonAlpha) (MIT, small research repo) | [MCTS scheduler](https://github.com/AutoResearch-Factory/AgonAlpha/blob/main/scripts/mcts.py), [unit tests](https://github.com/AutoResearch-Factory/AgonAlpha/blob/main/scripts/tests/test_mcts.py), [proposer](https://github.com/AutoResearch-Factory/AgonAlpha/blob/main/agents/alpha-proposer.md), [reviewer](https://github.com/AutoResearch-Factory/AgonAlpha/blob/main/agents/alpha-reviewer.md) | MCTS lineage allocation, exploration/exploitation, specialized independent scientific reviewer | **High research fit; do not copy scorer.** Important finding: CLI \`cmd_update\` accepts a caller-supplied finite numeric \`--score\`, and updates tree state; it does **not** enforce a cryptographic link to reviewer-attested evidence. Reviewer instructions are separate markdown/prompt procedure. NRFX must admit score only from independently verified immutable replay |
| [algorithmicsuperintelligence/openevolve](https://github.com/algorithmicsuperintelligence/openevolve) (Apache-2.0) | [controller](https://github.com/algorithmicsuperintelligence/openevolve/blob/main/openevolve/controller.py), [evaluator](https://github.com/algorithmicsuperintelligence/openevolve/blob/main/openevolve/evaluator.py), [program database](https://github.com/algorithmicsuperintelligence/openevolve/blob/main/openevolve/database.py), [parallel worker](https://github.com/algorithmicsuperintelligence/openevolve/blob/main/openevolve/process_parallel.py) | Multi-island / MAP-Elites diversity, program evolution, population resume, separate evaluator | **Research design reuse; not a drop-in runner.** Evaluators import/execute supplied Python evaluator modules; generated program execution needs a strict isolated process, no-network sandbox and an allowlisted formula AST, not unrestricted code against the private Gold ZIP. A timeout alone is not security |
| [CamusGIT/EvoQuant](https://github.com/CamusGIT/EvoQuant) (Apache-2.0) | [skills directory](https://github.com/CamusGIT/EvoQuant/tree/main/EvoQuant/skills), [skills README](https://github.com/CamusGIT/EvoQuant/blob/main/EvoQuant/skills/README.md) with \`local-paper-navigator\`, \`quant-paper-extractor\`, \`quant-experiment-runtime\`, \`research-ideation\`, \`experiment-pipeline\`, \`evo-memory\`; large tests tree | Scientific source-to-hypothesis memory with citation lineage and reproducible experimental questions | **Use structured knowledge/evidence schema only.** Full chat/channel/skills gateway is expensive and duplicates existing NRFX control plane; paper-derived formulae must pass causal audit and same engine |
| [ilasek/trading-autoresearch](https://github.com/ilasek/trading-autoresearch) (no GitHub-detected/root LICENSE in reviewed tree) | [frozen experimental protocol](https://github.com/ilasek/trading-autoresearch/blob/main/engine/protocol.py), [protect-engine GitHub workflow](https://github.com/ilasek/trading-autoresearch/blob/main/.github/workflows/protect-engine.yml), [ranking](https://github.com/ilasek/trading-autoresearch/blob/main/engine/ranking.py), [costs](https://github.com/ilasek/trading-autoresearch/blob/main/engine/costs.py), [research program](https://github.com/ilasek/trading-autoresearch/blob/main/program.md) | Explicit immutability barrier: strategy agents may not rewrite evaluator/cost code; error bars, paired bootstrap, diverse mechanism clustering, multi-family scout/challenge budgets | **Strong protocol reference, NOT copyable before license grant.** Repeated holdout vetoes or adaptive reaction to their outcome contaminate the holdout even if the holdout is never used as a scored objective. Prefer sealed one-use prospective gate |
| [rustyeddy/trader](https://github.com/rustyeddy/trader) (BSD-2-Clause, currently small Go research repo) | [execution quality](https://github.com/rustyeddy/trader/blob/main/internal/executionquality/measure.go), [determinism regression](https://github.com/rustyeddy/trader/blob/main/internal/backtest/determinism_test.go), [OANDA marketdata reader](https://github.com/rustyeddy/trader/blob/main/internal/marketdata/internal/provider/oanda/client.go), [OANDA account activity](https://github.com/rustyeddy/trader/blob/main/internal/adapters/accountactivity/oanda/client.go) | Exact currency/quantity arithmetic, event journals, broker-fill vs quote-touch slippage, missing values stay \`UNKNOWN\` | **High architecture fit for broker reconciliation.** In inspected \`internal/adapters/broker/\`, the concrete broker adapters were \`alpaca\` and \`sim\`; OANDA marketdata/account-activity adapters exist but **an OANDA order-placement adapter was not evidenced**. Do not claim tested OANDA execution or production readiness |
| [nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest) (MIT) | [upstream implementation and docs](https://github.com/nkaz001/hftbacktest), [full-depth replay](https://hftbacktest.readthedocs.io/en/latest/) and [accelerated limitation](https://hftbacktest.readthedocs.io/en/latest/tutorials/Accelerated%20Backtesting.html) | Feed/order latency, L2/L3 depth, queue-position and partial-fill simulation | **Only if actual licensed tick/order-book depth exists**. Our historic Gold M1 BID/ASK has no L2/L3 queue, so adopting this now risks fabricating realistic-looking executions. Its accelerated mode explicitly omits some fill/latency effects |
| [Optima-CityU/LLM4AD_Next](https://github.com/Optima-CityU/LLM4AD_Next) (BSD-3-Clause) | [src/llm4ad](https://github.com/Optima-CityU/LLM4AD_Next/tree/main/src/llm4ad) \`planner\`, \`coder\`, \`evaluator\`, \`orchestrator\`, \`memory\`, \`agent\` | Broad general-purpose algorithm discovery and modular evaluator interfaces | **Benchmark only, large integration footprint**. No NRFX performance proof, and no reason to replace our immutable engine until a bounded benchmark wins on identical tasks |
| [ashutosh99sri-cyber/paper-trading-research-agent](https://github.com/ashutosh99sri-cyber/paper-trading-research-agent) (MIT) | [published negative result and reports](https://github.com/ashutosh99sri-cyber/paper-trading-research-agent) | Conservative paper-only gates, negative controls, reproducible walk-forward failure reports | **Reference for honest publication of rejection**; self-reported outcomes are not independently certified |
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) (license not independently cleared in this review) | [project methodology](https://github.com/karpathy/autoresearch) and quant adaptation above | Short edit-run-score-retain loop under immutable scoring protocol | **Template concept only**; not an autonomous FX backtesting engine; avoid blind reuse of holdout results or data in git |
| [AutoResearch-Factory/AgonAlpha paper](https://arxiv.org/abs/2608.11250) | Research methodology claims, not independent broker results | Tree search over full experiment artifacts, not just single metrics | Separate design inspiration from evidence of deployable software or Alpha on XAUUSD |

### Specific vulnerability and evidence lessons

**Untrusted numeric fitness is NOT an audit.** In AgonAlpha, the source
\`mcts.py\` finite-score check is necessary but insufficient: the caller can
provide an arbitrary finite score without carrying replay evidence. NRFX
should define one \`VerifiedFitness\` receipt that can only be created after:
(1) frozen hypothesis/code/source signature checks, (2) reference/fast
agreement where supported, (3) ledger/monthly/weekly/cost reconciliation,
(4) allowed training-window gate, (5) independent reviewer verdict. An
agent/LLM/MCTS must never directly write official \`fitness\` or \`PASSED\`.

**Holdout is not fresh forever.** trading-autoresearch's author documents
that the designated holdout is a *veto* rather than a ranking objective.
That reduces direct optimizer pressure, but any repeatedly observed veto
can leak information into subsequent adaptive proposals. A prospective
NRFX acceptance test must preregister *one final family/candidate*
and one evaluation moment; any re-search following rejection requires
an entirely newer and independently sealed period.

**Broker truth can be unknown.** rustyeddy's execution-quality module
stores unresolved benchmark/currency conversion as *unknown*, not
mathematically zero. NRFX must never assign zero slippage when no broker
quote benchmark exists. OANDA candle BID/ASK, account transaction tape
and real fill timestamps require distinct provenance and explicit joins.

**Missing market depth is not simulated depth.** Full HFT market-order-book
replay offers powerful test design but cannot reconstruct queue position,
broker market impact or partial fills from M1 OHLC alone. Keep
\`execution_assumption=M1_SYNTHETIC\` unless genuine tick/depth sources
and their usage rights pass separate audit.

**Fixed experiment law must be enforceable.** A strategy's generated
Python must not modify tests, fees, parser, execution, holdout access,
deployment or risk controls. Github workflow path checks are useful
regression controls but **not enough** on their own: untrusted agent code
should execute only inside a resource-bounded sandbox with no network,
secrets or mounted holdout/original source (provide sanitized inputs).
Only the deterministic runner receives authorized private quotes.

### Prioritized bounded adoption spikes — no external code copied

| Priority | Deliverable | Pass/fail criterion |
| --- | --- | --- |
| P0 / A | \`VerifiedFitness\` admission gate on *existing canonical factory* | Forged MCTS score, changed code SHA, missing evidence, wrong $0.40/oz XAU contract, partial months, reviewer conflict and holdout peeking all BLOCK; exact valid local training replay passes |
| P0 / B | Unified experiment lifecycle + permission graph (propose/evaluate/audit/observe) | one canonical immutable evidence identifier across math director, family grids, console and unattended service; no extra independent owner |
| P1 / C | Broker fill reconciliation pilot from private OANDA practice transactions | quote touch known vs unknown, side-specific BID/ASK, account currency, units, filled/partial/uncertain status, spread/financing, duplicate event IDs and crash replay |
| P1 / D | Two population selection baselines against fixed arithmetic grammar | MCTS vs uniform/random vs mutation under exactly matched candidate and compute budgets; all use same evaluator, training only, report diversity/duplication and validation sensitivity |
| P1 / E | Knowledge/citation bridge from curated papers | hypothesis with paper/source excerpt, information cutoff, formula AST, no executable free-form code; reruns reproducible |
| P2 / F | Full source-depth HFT spike | **SKIP** unless a licensed, independently fingerprinted L2/L3 data source exists; prefer tick BID/ASK source cross-check first |
| P2 / G | Optuna / OpenEvolve / generic LLM4AD cross-family algorithm experiment | sandbox and cost cap with explicit kill, no changes to frozen evaluator; requires demonstrable improvement to justify dependency |
| P3 / H | Full host fault-injection | exactly-once state transition, crash recovery with clean replay, no green false success, no private source upload; actual host needed |

### Scorecard for decisions (qualitative, not GitHub stars)

- **Adopt design immediately:** AgonAlpha's *separate independent review*
  plus bounded MCTS idea; trading-autoresearch's protocol hardening,
  benchmark-aware uncertainty and correlated-family accounting;
  rustyeddy's exact trade/account/currency event provenance.
- **Pilot behind a measurable gate:** OpenEvolve's island diversity
  search, EvoQuant's paper memory, Optuna/LLM4AD optimizer comparison.
- **Do not integrate yet:** hftbacktest without order-book data, large
  agent frameworks that duplicate our supervisor, live broker execution,
  uncertain-license source code.
- **Keep the old scientific evidence:** Existing 2012–2026 historical
  exposure, negative strategy results and 13-field parity ledgers are
  never rebranded as prospective OOS or live execution.

**Architectural decision:** the path to a strong No Risk FX platform is
not to copy more "Grok Bot" repos. It is to put an **auditable, typed
independent verification gate** between every proposed mathematical
idea and the one canonical deterministic research/execution engine,
then validate real broker-fills separately from synthetic profit.


## Phase IV: Operational completeness and external system selection (2026-11-03)

### Exact code-base baseline and research boundaries

Checked current \`feat/quant-engine-foundation\` Draft PR #1. The code base
already has a Python 3.12 CI workflow, \`constraints-ci.txt\`, a full pytest
step, \`norisk_quant\` engine, independent service/director and local QuantLab.
It does **not** have one authoritative multi-family execution and experiment
ledger, a production host acceptance report, or independently demonstrated
prospective FX/XAU edge. CI does **not** have the private original market ZIP,
nor proof of broker-side execution. No new vendor should be installed just
because its feature appears on an architectural checklist.

### New research: external candidates, concrete caveats and decision

| Source | Verified capability / crucial caveat | Decision for NRFX |
| --- | --- | --- |
| [Feast point-in-time join guide](https://github.com/feast-dev/feast/blob/master/docs/getting-started/concepts/point-in-time-joins.md) (Apache-2.0) | **Critical finding:** default PIT join filters on event timestamp, but a later backfilled correction may still be returned. When supported, \`filter_by_created_timestamp=True\` also requires \`created_timestamp <= entity_timestamp\`. Not all stores support it and a source-side falsified created time still leaks. | Adapt *availability timestamp semantics* to our current strict macro \`released_at / first_seen_at\` contract and write adversarial leak tests. Do **not** deploy full feature server first |
| [Pandera](https://github.com/unionai-oss/pandera) (MIT) | DataFrame schemas with strict columns, row/column bounds and dtype constraints, supports pandas/Polars/Arrow. Coercion may mask raw ingestion faults if used carelessly. | Pilot on closed OANDA BA bars and source-level rejection, not on private baseline until equivalence |
| [MLflow dataset tracking](https://mlflow.org/docs/latest/dataset/) (Apache-2.0) | Dataset fingerprint, origin lineage, experiment tags and stored artifacts. Tracking metadata does not independently certify a backtest or prevent revised economic feature leakage. | Lightweight experiment read model only if existing immutable JSON/Parquet manifests are insufficient |
| [DuckDB](https://github.com/duckdb/duckdb) (MIT) | Efficient local SQL aggregation of Parquet, analytical join across monthly/weekly/robot audits. A DuckDB database is not a writer authorization or broker source of truth. | Prefer a read-only analytical view, preserving existing source hashes and one canonical ledger |
| [Evidently](https://github.com/evidentlyai/evidently) (Apache-2.0) | Observability on missing-value rate, drift, unusual spread/volatility/news distributions. Drift alone does not prove strategy decay or license retraining on holdout. | Add monitoring metrics and alarms before introducing a permanent drift service |
| [Temporal Python SDK](https://github.com/temporalio/sdk-python) (MIT) | Durable event-driven long-running orchestration with deterministic workflow replay; requires external service and workflow/worker separation. The SDK sandbox catches nondeterminism, **not malicious code execution**. | Defer until measured failure of a single-host supervisor plus SQLite state journal |
| [Dagster](https://github.com/dagster-io/dagster) (Apache-2.0) | Asset lineage, pipeline definitions, data quality checks and UI. A whole second scheduler would duplicate QuantLab. | Benchmark only against concrete 7-day failure/resume requirements |
| [holdout](https://github.com/DaniyalMlk/holdout) (MIT) and [backtest-guard](https://github.com/AgentJDrew/backtest-guard) (MIT) | Candidate-family DSR/PSR/PBO, multiple-testing penalties, purged CV and worked examples. Returns series must use consistent units, frequency, non-i.i.d. treatment and honest count of tried candidates. Small repositories, so rerun their claims independently. | Standalone research *statistical audit* benchmark on synthetic null + known edge, then controlled training-only exports |
| [PySR](https://github.com/MilesCranmer/PySR) / [official docs](https://pysr.ai/dev/) | Complex symbolic nonlinear expressions with constrained operators, custom losses and complexity penalties. Julia/runtime overhead and unrestricted operators can create noncausal/unstable expressions. | Run **isolated CPU/complexity benchmark** against existing arithmetic grammar; use AST whitelist, capped depth, no private holdout/host execution |
| [gplearn](https://github.com/trevorstephens/gplearn) | Genetic programming symbolic expression trees, crossover/mutation, parsimony and correlation-based candidate reduction. Fitness on price prediction is not equivalent to executable after-cost P/L. | Low-cost baseline before PySR; every proposed formula goes through the canonical evaluator |
| [Pydantic AI](https://github.com/pydantic/pydantic-ai) | Typed AI agent output with validation, usage limits, optional human approval; output schemas are not code sandbox or truthful research evidence. | Pilot structured Grok/Qwen hypothesis plan, **no broker tools or arbitrary Python execution** |
| [Langfuse](https://github.com/langfuse/langfuse) | Agent trace/cost/prompt versions, MIT except \`ee\` folders; self-hosted telemetry documented. It can inadvertently capture sensitive quotes, sources and credentials. | Optional redacted AI-cost tracing only, no market data/prompt secrets; avoid heavyweight stack initially |
| [GitHub Actions secure use guide](https://docs.github.com/en/actions/reference/security/secure-use) | Use workflow dependency lockfiles where possible; otherwise full-length action commit pins, minimal GITHUB_TOKEN privileges, restricted triggers. | **Implemented** in the accompanying workflow change: exact official checkout v4, setup-python v5 and upload-artifact v4 commit SHAs plus security regression |

### Crucial official broker + macro controls

- OANDA [REST API development guide](https://developer.oanda.com/rest-live-v20/development-guide/)
  documents 120 REST requests/s per IP, 20 streaming connections per IP,
  and at most 2 *new* connections/s. Our eventual data collector must bound
  requests/backoff, reuse sessions and avoid 1 stream per robot.
- OANDA [account state polling](https://developer.oanda.com/rest-live-v20/account-ep/)
  exposes \`/v3/accounts/{accountID}/changes?sinceTransactionID=...\` and
  \`lastTransactionID\`. The [transactions endpoint](https://developer.oanda.com/rest-live-v20/transaction-ep/)
  exposes \`/transactions/sinceid?id=...\` with full event IDs.
  A future **read-only** practice reconciler should persist a high-water ID
  atomically **with** accepted journal rows, detect duplicates, require matching
  instrument/units/time, and not silently infer missing transactions from a
  stale cursor. Stream heartbeats are *liveness*, not fill confirmation.
- OANDA [Instrument schema](https://developer.oanda.com/rest-live-v20/primitives-df/)
  provides \`pipLocation\` and \`displayPrecision\` along with trade unit and
  margin rules. Never reapply XAU USD-per-ounce cost semantics to EUR_USD,
  USD_JPY or varying account currencies.
- [ALFRED vintage dates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)
  and [FRED observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
  operate primarily with **YYYY-MM-DD** real-time periods. FRED
  [release dates](https://fred.stlouisfed.org/docs/api/fred/release_dates.html)
  need not be the time the data became available through FRED. Intraday
  macro trading needs original release timestamp and actual captured
  availability timestamp. A date-only vintage can never authorize an
  M1 news-reaction backtest.

### Lean target architecture (one owner per invariant)

| Concern / canonical owner | Required action / test | Reject the alternative |
| --- | --- | --- |
| Market data | existing canonical M1 importer + source SHA manifest; provider adapters are read-only, immutable and timestamped | second arbitrary quote schema / late corrections mislabeled historical |
| Macro feature view | one PIT normalizer: \`released_at <= first_seen_at <= decision_at\`, valid value vintage/source and timezone; future corrections hidden | today's latest FRED values copied across old M1 dates |
| Formula agents | isolated expression AST from bounded Grok/Qwen/GP proposal, canonical validation and resource budget | AI writing engine/evaluator/risk/holdout access |
| Experiment lifecycle | one local SQLite WAL append-only *index* referencing immutable private evidence artifacts and SHA lineage; checkpoint transaction owner | separate independently mutable JSON states across controller/director/UI |
| Execution economics | deterministic per-instrument quote side, lots/units, account conversion, financing and fee specs; preserve old frozen XAU \`0.40/oz ALL-IN\` historical contract | universal FX fee, “filled” label from candle touch alone |
| Fitness authority | score computed ONLY after external independent evidence reconciliation; agent results remain unverified proposals | caller/LLM-supplied fitness accepted as scientific result |
| Scientific validation | training-only selection, purged/embargoed temporal CV, cumulative tested-family accounting, **one-use future holdout** | repeated adaptive holdout veto and leaked macro |
| Analytics | DuckDB read-only over Parquet/SQLite; make dashboard a projection | dashboard writing states or recreating its own report values |
| Operations | existing single-host supervisor first; real restart/kill/disk/network outage drill before introducing Temporal/Dagster | 3 simultaneous “owners” issuing jobs, green heartbeat without host |
| Security | no public dataset/token; pin GitHub actions to exact SHA; source-only CI, separate practice-only permission boundary, no live API adapter until explicitly authorized | public raw ZIP, PR automation with production secrets |

This is a **target contract**, not a report that all components exist or have
passed live end-to-end validation. “100%” can only mean defined acceptance
criteria satisfied on a pinned release, not a guarantee of positive monthly
returns or permanent correctness.

### Non-negotiable acceptance suite to call the engineering release complete

1. One exact pinned Git SHA; full suite green; 2012 private original 689 x 13
   trade-field archived parity, plus independent XAU frozen negative-control
   reproduction. Keep multi-year timed-out runs marked NOT PASSED.
2. Synthetic 5-asset campaign with at least 3 agent families, one *shared*
   planner, one immutable registry and exactly-once recorded outcomes; both
   incompatible signals and missing data yield ABSTAIN.
3. PIT negative controls: a backfilled headline, revised NFP and policy rate,
   delayed first_seen_at, scheduled-release revision and US/EU DST all unable
   to leak into the prior trading decision.
4. Frozen training design vs one-use prospective validation: failed or rejected
   strategies not reworked on observed holdout; null-data multiple-testing
   rejection rate tested under seeded simulations.
5. OANDA **practice** read-only transaction replay + crash-and-restart from
   high-water transaction ID; reconcile partial fills, financing, unknown
   slippage, currency units and duplicates from captured *private* events.
   This alone does not enable live trading.
6. Real 24/7 provisioned host with a 7-day monitored campaign, disk-full,
   forced kill, reboot and transient network interruption, no double job,
   measured CPU/RAM/IO and cost limits.
7. CI security guard + dependency vulnerabilities/licenses reviewed; no
   external code copied under unknown or restrictive license, secrets kept
   outside workflows/output, role boundaries audited. Repo visibility
   remains Public until the owner explicitly changes it.
8. Unified UI backed by read-only canonical states; when any source, host,
   pending experiment or provenance validation fails, UI must show BLOCKED
   rather than falsely READY.

**Adoption order:** freeze evidence contract -> unify scheduler -> broker
ledger/FX mechanics -> time-aware macro -> independent fitness -> optimizer
spikes -> UI/monitoring -> independent holdout/host operational acceptance.
Avoid simultaneously installing Feast, Temporal, Dagster, MLflow, PySR and
Langfuse: that would increase attack surface, cost, and technical debt before
we have one trusted canonical engine.
