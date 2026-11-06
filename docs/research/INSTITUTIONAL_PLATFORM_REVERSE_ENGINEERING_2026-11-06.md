# No Risk FX — Institutional Platform Reverse Engineering, Round 1 (2026-11-06)

**Scope:** Public, observable architecture and published API behaviors of Bloomberg B-PIPE, LSEG Real-Time, Trading Technologies, Saxo OpenAPI, Interactive Brokers, TradingView, Bookmap, Nasdaq TotalView, Databento, BlackRock Aladdin, and MetaTrader 5. This document does **not** claim possession of proprietary source code, implementation internals, paid data access, rights to redistribute any feed, or measured latency. It is an independently designed engineering blueprint, not a vendor implementation.

**Project constraint:** No new live trading and no original historical gold research triggered by this design; it is a specification and verification plan only.

## 1. Evidence register — confirmed vendor behaviors versus proposed design

| Product | Publicly documented behavior | Transferable engineering pattern | Limitation |
|---|---|---|---|
| Bloomberg B-PIPE | Consolidated, normalized real-time feed spanning the Terminal's multi-asset coverage | Feed adapter + canonical instrument master + provenance | Data licensing, entitlement, provider costs unknown for NRFX |
| LSEG Real-Time | WebSocket API with cloud and on-prem distribution; optimized conflated quote feed, optional full tick | Capability-level QoS and no loss of event semantics | Conflation unsuitable where every order-book event is required |
| Trading Technologies (TT) | Hybrid cloud/edge: low-latency market data/order routing via edge; risk/admin via REST; reconnect/resync | Split latency-critical and administrative planes; reconcile state after disconnect | NRFX does not require exchange co-location for an analytics-first product |
| Saxo OpenAPI | Per-resource subscriptions, snapshot and delta updates; a delta can arrive before the HTTP snapshot; separate quote resources | Sequence-guarded snapshot/delta state machine; quote validity metadata | Account capability and redistribution agreements mandatory |
| Interactive Brokers (IBKR) | Live/frozen/delayed/delayed-frozen market data modes and API subscription/pacing limits | Explicit quote quality and entitlement state; pacing governor | Gateway subscription is not equivalent to unrestricted data distribution |
| TradingView Advanced Charts | Historical getBars; realtime subscribeBars; multiple dataset-specific listeners; complete bar replacement, strict timestamps | Independent chart projection service and subscription lifecycle | Client chart cache does not replace server-side event log |
| Bookmap | Historical book-depth heatmap, executed volume dots, BBO and indicators; full order flow requires supporting market data | Distinguish displayed book depth, executed trades and inferred liquidity | Do not label inferred CFD zones as exchange order book |
| Nasdaq TotalView | Displayed order depth for specific Nasdaq market center, not all possible markets | Venue-scoped L2/L3 provenance and coverage disclosure | A venue order book is not the entire global market |
| Databento | Separate schemas for L0 OHLCV, L1 BBO/trades, L2 MBP, L3 MBO; dual event/receive timestamps; live/historical schema alignment | Typed data contracts and matching replay/live semantics | Availability, fee and rights depend on dataset |
| BlackRock Aladdin | Unified multi-asset positions/risk/what-if scenarios in common investment data language | Unified risk/exposure ontology and scenario engine | Cannot replicate proprietary models from public descriptions |
| MetaTrader 5 | Python tick history: time/bid/ask/last/flags; DOM APIs require subscriptions; UTC timestamps | Broker adapter for private analytics and quote comparison | MT5 DOM is broker-specific, may not be exchange-wide |

Official references:
- Bloomberg: https://professional.bloomberg.com/products/data/enterprise-catalog/real-time-data-feed/
- LSEG: https://www.lseg.com/en/data-analytics/market-data/data-feeds and https://developers.lseg.com/en/api-catalog/real-time-opnsrc/websocket-api
- TT: https://library.tradingtechnologies.com/apis/tt-net-sdk/getting-started-with-tt-net-sdk/product-architecture-2/ and https://tradingtechnologies.com/compliance/risk-management/
- Saxo snapshot/delta: https://www.developer.saxo/openapi/learn/high-level-overview and pricing https://www.developer.saxo/openapi/learn/pricing
- IBKR modes: https://www.interactivebrokers.com/docs/tws-api/doc/md/delayed-data and pacing https://www.interactivebrokers.com/docs/tws-api/doc/pacing-limitations
- TradingView: https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/required-methods/ and https://tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/datafeed-subscriptions/
- Bookmap: https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapMainChart
- Nasdaq: https://www.nasdaq.com/products/data/equities/nasdaq-totalview/depth-data
- Databento: https://www.databento.tech/docs/schemas and https://www.databento.tech/docs/schemas/mbp-1
- Aladdin: https://www.blackrock.com/aladdin/platforms/products/aladdin-risk
- MetaTrader 5: https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksfrom_py and https://www.mql5.com/en/docs/python_metatrader5/mt5marketbookget_py

## 2. Seven design conclusions for No Risk FX

1. **Immutable raw feed first.** Every admissible input is captured with raw payload, source ID, schema version, instrument alias, event timestamp and receipt timestamp. Never destroy raw metadata during normalization.
2. **Instrument identity before price comparison.** XAUUSD OTC spot/CFD, COMEX gold futures, spot FX, Dow Jones cash index, DJIA-linked CFDs, and DJ futures are different instruments, venues and economics. Comparing them requires explicit mapping and basis/contract assumptions, *not* simply renaming every instrument to one symbol.
3. **Quote quality is a first-class state.** Mark LIVE / DELAYED / FROZEN / STALE / DISCONNECTED / NO_ACCESS / INDICATIVE with provenance, permission and age. Do not silently substitute delayed quotes inside an actionable live calculation.
4. **Snapshot/delta recovery is deterministic.** When a feed uses snapshots and deltas, buffer updates until a consistent snapshot/sequence barrier; on sequence gap, mark stream unavailable and re-sync, never produce fictitious order-book continuity.
5. **Separate market inference from evidence.** A candle-derived liquidity zone is an inference. L2/L3 depth is observed *venue-specific displayed liquidity*. Executed trades are a different evidence class. A market-wide gold liquidity map cannot truthfully be inferred from one CFD broker's DOM.
6. **Risk decisions precede trade execution.** Exposure, drawdown, order sanity and margin checks belong to independent, auditable pre-trade controls; research and display services cannot override these gates.
7. **Data-rights gate per source and usage.** Internal analytics, public display, commercial redistribution and AI/model use require distinct permission checks, rather than trusting possession of API credentials. Saxo's 2026-10-05 support article explicitly distinguishes private storage/backtesting from redistribution: https://openapi.help.saxo/hc/en-us/articles/39663625431581-Can-I-store-and-use-OpenAPI-market-data-for-my-own-algo-or-AI-backtesting

## 3. Proposed internal logical architecture

```text
[Brokers' MT5 terminals]      [Licensed exchange/venue feed]      [Reference/news/economic feeds]
           |                               |                                |
           +-------------------------------+--------------------------------+
                                           |
                                 SOURCE ADAPTERS
                     (auth, permissions, reconnect, rate caps)
                                           |
                           RAW IMMUTABLE EVENT JOURNAL
                          (source, ingest time, raw payload)
                                           |
                    INSTRUMENT MASTER + CANONICAL NORMALIZER
                 (currency, contract size, bid/ask, time, venue)
                                           |
                    DATA QUALITY + ENTITLEMENT DECISION ENGINE
                      (lag, gap, duplicate, stale, rights)
                                           |
                     +---------------------+-----------------+
                     |                     |                 |
             LIVE SNAPSHOT STORE       HISTORY/REPLAY    DERIVED SIGNALS
                & SUBSCRIPTIONS          STORAGE          & MARKET EVENTS
                     |                     |                 |
                  API GATEWAY         QUANT ENGINE      EXPLAINABILITY
                     |                     |                 |
                     +---------------------+-----------------+
                                           |
                        RISK / PORTFOLIO / SCENARIO SERVICE
                                           |
                        SUBSCRIPTIONS, USER APP, ALERTS
```

This is **NRFX's proposed architecture**, not an assertion that any compared vendor uses this exact diagram.

## 4. Canonical data contracts (draft)

### 4.1 InstrumentIdentity
```json
{
  "canonical_id": "XAUUSD.SPOT.BROKER_A",
  "asset_class": "spot_cfd",
  "underlying_id": "XAU",
  "quote_currency": "USD",
  "venue_or_broker": "BROKER_A",
  "broker_symbol": "XAUUSDm",
  "contract_size": null,
  "tick_size": null,
  "trading_calendar_id": null,
  "effective_from_utc": null,
  "mapping_version": 1
}
```
A null here requires instrument-specific discovery/validation; it is *not* a production-ready instrument.

### 4.2 QuoteEvent
```json
{
  "source_id": "mt5_broker_a_account_a",
  "instrument_id": "XAUUSD.SPOT.BROKER_A",
  "event_ts_utc_ns": null,
  "ingest_ts_utc_ns": null,
  "bid": null,
  "ask": null,
  "last": null,
  "size": null,
  "feed_type": "broker_quote",
  "market_data_state": "LIVE",
  "rights_class": "INTERNAL_ONLY",
  "raw_event_ref": null,
  "session_id": null,
  "sequence": null
}
```
This is a conceptual schema. Source clocks can be inaccurate, some events lack sequence IDs, and not every feed is licensed for persistent storage.

### 4.3 LiquidityEvidence
```json
{
  "instrument_id": "GC.FUT.VENUE",
  "evidence_type": "DISPLAYED_ORDER_BOOK_DEPTH",
  "scope": "VENUE_ONLY",
  "level": "L2_OR_L3",
  "source_id": null,
  "event_ts_utc_ns": null,
  "price": null,
  "displayed_quantity": null,
  "quality_flags": []
}
```
Allow separate evidence types `EXECUTED_TRADE`, `CFD_BROKER_DOM`, `INFERRED_PRICE_ZONE`. Do not rank them as equivalent.

## 5. Multi-broker MT5: what is and isn't learned

**Can test with actual terminals:** tick frequency, spread distribution, reconnect behavior, session timing, timestamp skew, quote divergence, broker-specific symbols, whether optional DOM exists, and gaps around news events. Python MT5 supports copy_ticks_from / copy_ticks_range and market_book_*.

**Cannot infer solely from these terminals:** the universal true price for OTC FX/gold, total global liquidity, hidden orders, every exchange trade, or blanket license to show broker prices to NRFX subscribers.

A broker comparison needs a *quality-weighted observation set*, not arbitrary median price blindly used as executable price. We should display each broker's executable quote separately, and any synthetic cross-provider reference as a clearly labeled analytical benchmark.

## 6. Streaming state machine (design requirement)

States: DISCONNECTED -> CONNECTING -> AUTHENTICATED -> SNAPSHOT_PENDING -> SYNCING -> LIVE, plus STALE / DEGRADED / NO_ACCESS. 
- Every session has a source identity, quote capability and permission result.
- Save event-time and receive-time separately; monitor latency and clock skew.
- For snapshot/delta feeds: buffer updates during snapshot setup, reconcile ordering, apply only consistent deltas, detect unresolvable gaps and resubscribe.
- Reconnect with exponential backoff and jitter; re-subscribe only active instruments; avoid exceeding provider pacing.
- If timestamps are not reliable or provider sequences unavailable, explicitly lower the assurance of deterministic order-book reconstruction.
- Never call a delayed or frozen price live. Historical bars are not interchangeable with raw ticks.

## 7. Product intelligence application

An NRFX Gold/FX/Indices analysis response should contain:
- **What changed:** instrument-specific quote and market/event regime.
- **Evidence:** sourced observed data, inferred analytical levels, and the exact period considered.
- **Decision conditions:** e.g. break/hold/retest of a level, *not* certainty of a profitable trade.
- **Risk:** invalidation, spread/volatility warning, upcoming event and maximum hypothetical loss.
- **Data quality:** age, permission, source type, lag and mismatches across providers.
- **Alternatives:** bull/bear/no-trade scenarios with objective invalidation criteria.

For the Dow 30 stock dashboard, use actual constituent securities and instrument identity; a Dow CFD broker feed alone cannot yield accurate underlying stock order-book microstructure. Corporate actions, market sessions and currency must be instrument-specific.

## 8. Contract tests / review gates

- Feed authorization: refuses real-time serving without verified rights and active session permissions.
- Normalization: source precision preserved; untrusted alias mapping rejected; negative spread/invalid tick/UTC errors rejected or quarantined.
- Source identity: spot CFD vs futures and exchange stock distinctions remain visible after aggregation.
- Replay: immutable raw events reconstruct same canonical outputs at pinned code+mapping version.
- Subscriptions: multiple chart resolutions coexist; short-lived subscriptions are cleaned up; snapshot/delta reordering is exercised.
- Gaps: lost sequences, reconnect, DST, holidays, event-time/receive-time inversion and delayed fallback all fail visibly.
- Data provenance: Every chart level or alert can be traced to a raw snapshot or a versioned inference rule.
- Latency: record empirical p50/p95/p99 freshness per provider after a real measurement session; set no unmeasured SLA.
- User-facing truthfulness: inferred zones are never displayed as full-depth exchange liquidity.

## 9. Recommended review order (no code merge yet)

**A.** Sign off on canonical instrument identity + evidence types + data-rights matrix.  
**B.** Build replayable ingest harness on fully synthetic, permitted samples with recovery failure-injection.  
**C.** Privately test selected MT5 demo feeds as broker-specific observations only; log gaps/permissions.  
**D.** Decide whether licensed futures/stock exchange depth data is commercially viable before promising Bookmap-like true liquidity.  
**E.** Connect research/backtest engine to the canonical read-only event contracts only after QA.  

**Non-goals this round:** no reverse-engineered proprietary code, no bypassing exchange/broker restrictions, no opening trades, no original gold strategy search, no unverified performance claims, no marketing public data as exchange-certified.

## 10. Explicit unknowns (require evidence, not speculation)

- Each broker's terms for collection, retention, display and commercial use.
- Tick/DOM availability and frequency on the actual NRFX accounts and symbols.
- Estimated paid L2/L3 provider pricing and license complexity for commercial distribution.
- Entitlement requirements for internal model training and serving derived analytics commercially.
- Hardware- and region-specific live latency metrics.
- Whether user-specific order execution is in scope; if so, additional control and regulatory obligations.

**Decision:** Architect a multi-provider, evidence-labeled analytics platform with immutable feed provenance and strict rights/quality gates. Integrate the existing quant engine behind this layer; do not restart the engine or misclassify a broker CFD quote as central exchange liquidity.
