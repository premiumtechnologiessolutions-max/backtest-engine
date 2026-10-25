# XAUUSD gap classification — audit 2010–2026 (2026-10-25)

**Status: empirical audit of timestamps; not verified historical broker trading calendar, not fill validation.**

Source: user-provided `Gold data.zip` (NOT committed), SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
2010-01-01 to 2026-09-20, 17 yearly files, **5,936,421 M1 candles** (BID/ASK OHLC). Converted UTC timestamps to America/New_York with DST.

Across consecutive candles INCLUDING 16 year boundaries:
- 15,558 intervals > 1 minute
- **4,019 intervals with more than 10 fully missing minutes**
- 2,904 daily-break timing matches near 17:00–18:00 New York time
- 707 regular Fri-to-Sun weekly timing matches
- 104 US-holiday special-hours **candidates**
- 59 holiday + weekend **candidates**
- 107 weekend windows with nonstandard close/reopen
- 83 extended or fragmented daily rollover windows
- 18 Sunday reopening quote gaps
- **37 gaps unexplained by standard weekly/daily/selected US holidays**
- Total **408 intervals** assigned medium/low confidence to review. High confidence here is a match to the *time pattern*, never proof of the originating broker schedule.

Selected source observations:
- 2019-02-27 **03:28–03:45 UTC**: 16 missing minutes; independent reports document a CME Globex technical halt and **03:45 UTC** reopening. Spot quote feed is NOT CME; co-occurrence does not prove the whole CME halt is a spot XAUUSD quote blackout.
- 2014-08-22 **20:59 UTC** through 2014-08-25 **02:00 UTC**: atypically late reopening after weekend. An August 25 CME Globex delayed-open incident is reported; spot feed begins before some published CME reopening times, so not conclusive.
- 2020-03-13 **20:59 UTC** to 2020-03-15 **22:00 UTC**: standard weekend duration 2,940 missing minutes, although next BID open jumped **+$38.00/oz**. COVID volatility does not prove exceptional extra closure.
- 2012-10-29 (Hurricane Sandy) shows the regular 60-minute daily break; CME documented closing US equity index futures, NOT other electronic futures markets.
- 2012-06-12 **20:59 UTC** to 2012-06-13 **03:00 UTC**: 360 minutes; unexplained, independent source/broker quote feed confirmation required.
- Good Friday 2026: 2026-04-02 **20:58 UTC** to 2026-04-05 **22:00 UTC**: 4,381 missing minutes; calendar-consistent extended weekend.

Execution implications for research engine:
1. Never force-close an open position merely because no M1 bar exists for > 10 minutes.
2. Never fill an order at an invented bar inside a gap. On resumption, gap-through SL may execute at an adverse first-available price, not the stop level.
3. Keep explicit confidence codes `regular_daily_break_pattern`, `regular_weekend_pattern`, `holiday_special_hours_candidate`, `nonstandard_weekend_window`, `active_session_unexplained`; require broker-specific calendar evidence before promoting a *candidate* to verified closure.
4. Quarantine or sensitivity-test any strategy performance affected by 408 uncertain gaps; an economic event date correlation is not proof of the cause.
5. Fixed research cost remains **$0.40/oz ALL-IN per round trip**, no extra variable spread/commissions. Historic BID/ASK quality does not imply actual broker executions.

Runnable audit and complete 4,019-row CSV, manual-review list, and annual summary were produced separately as `NoRiskFX_XAUUSD_Gap_Audit_2010_2026.zip`. The ZIP is a conversation artifact, **not currently stored in the repository**; to reproduce, run its `classify_gold_gaps.py` over the original private ZIP.

Source examples:
- [CME gold GC hours](https://www.cmegroup.com/markets/metals/precious/gold.timeAndSales.html)
- [CME holiday schedules](https://www.cmegroup.com/trading-hours.html)
- [FOREX.com spot metals hours](https://www.forex.com/en/help-and-support/metals/)
- [Feb 2019 Globex outage, Reuters](https://www.lse.co.uk/news/update-1-derivatives-exchange-cme-group-halts-all-cme-globex-market-on-technical-issues-ho7uacfxdj67j7q.html)
- [2019 03:45 UTC Globex resumption](https://investinglive.com/news/%21/all-markets-on-cme-globex-will-preopen-at-0915-pm-ct-and-open-at-0945-pm-ct-20190227)
- [2014 delayed Globex opening](https://www.financemagnates.com/forex/analysis/futures-trading-halted-for-four-hours-on-cme-groups-globex-markets-platform/)
- [2012 Hurricane Sandy: index markets closure scope only](https://www.cmegroup.com/media-room/press-releases/2012/10/28/media_alert_cme_grouptocloseusequityindexfuturesandoptionsonfutu.html)
- [March 2020 CME electronic Globex remains open](https://investor.cmegroup.com/news-releases/news-release-details/cme-group-close-chicago-trading-floor-precaution)

**Limitations:** XAUUSD spot feed provider/contract and historical holiday schedules are not independently authenticated, so many classifications are provisional. Candle M1 cannot reveal intra-gap movement or genuine tick-level fills.