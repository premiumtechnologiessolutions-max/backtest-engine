# Frozen experiment NYM-01 — New York morning opening range (2026-10-26)

Status BEFORE any original-source backtest results: **PREREGISTERED, NO HISTORICAL METRICS EXAMINED**.

Two distinct causal hypotheses:
1. `ny_morning_breakout_0820_0900`: first complete post-open M5 candle closing beyond the 08:20–08:59 New York opening-range high/low by at least $0.25. Research directional continuation.
2. `ny_morning_rejection_0820_0900`: first post-open M5 candle wicking beyond that high/low by at least $0.25 then closing strictly back inside; fade the swept side. If one bar breaches BOTH ends, reject ambiguous candle.

Both use timezone-aware **America/New_York** (proper US DST conversion rather than hardcoded UTC offsets). Range must have exactly 40 contiguous original M1 BID-reference bars at 08:20–08:59 local. The trigger window is complete M5 candles closing at 09:05 through 11:00 NY. The trigger must open inside the completed range. At most one signal per strategy per NY local date. Signal confirmation at complete M5 close; fill at first available M1 open, not before. Stop distance from close to opposite prior range boundary for breakouts, or same trigger candle wick extremum for rejection, plus $0.10; allowed $0.75–$20. Target 1.8R; maximum holding 180 minutes from entry, exit at first observed M1 open at/after deadline, stops and targets prioritized per engine rules. No other intraday/session-based adjustment or earnings/news exclusion.

- Source **PRIVATE original Gold data.zip only**, expected SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. No market data to public GitHub.
- **Predeclared design years 2012 and 2013 only** initially, one-year-at-a-time execution with full monthly/weekly and floating-equity reports; years already historically exposed in other studies, NOT independent OOS.
- Single full-cycle cost **$0.40 USD/oz ALL-IN**, volume **1oz**, single Market position, reference-fast ledger reconciliation, stop-first, gap-through, max signal entry delay 1 min.
- **Predeclared promotion criterion per hypothesis**: >=16/24 positive calendar months across both years, positive total net after fees, and >=50 filled trades separately in each year. Else REJECT without retroactive parameter tuning, and do not open 2014–2016 for this candidate.
- If a hypothesis passes, open 2014–2016 *unchanged* as historically exposed secondary corroboration. Truly independent forward months not claimed. Even 12/12 historic months never guarantees future profit.
- Code `src/norisk_quant/ny_morning.py` and synthetic causal tests `tests/test_ny_morning.py` committed before examining historical results. Freeze implementation and exact settings prior to first private-data run.
