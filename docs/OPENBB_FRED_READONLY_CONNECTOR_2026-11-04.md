# Read-only OpenBB FRED adapter (2026-11-04)

A real optional import of upstream OpenBB's QueryExecutor/FredSeries path is now implemented in src/norisk_quant/openbb_fred_snapshot.py, integrated with the existing causal stream replay. This is not only a metadata bridge; at runtime, when OpenBB's provider package and a local FRED API key are installed, fetch_fred_snapshot invokes the original OpenBB QueryExecutor to fetch the single requested series.

Pinned review:
- https://github.com/openbq-org/OpenBB/blob/2a392e890f6eb1f0f4e3a71742720af8f056333a/openbb_platform/core/openbb_core/provider/query_executor.py
- https://github.com/openbq-org/OpenBB/blob/2a392e890f6eb1f0f4e3a71742720af8f056333a/openbb_platform/providers/fred/openbb_fred/models/series.py

**CRITICAL provenance limitation**: upstream FredSeriesFetcher drops FRED realtime_start/end information. An ordinary historical series requested in 2026 does not prove that the quoted vintage was known in 2012/2017/2020. Our adapter labels all fetched rows as first known at snapshot capture. It refuses all historical backtest approval and broker execution claims. The snapshot hash protects integrity but is not a trusted timestamp or historical-vintage attestation. It also does not prove the installed OpenBB runtime matches the pinned source revision.

Operational boundaries:
- Only provider 'fred', model 'FredSeries', single uppercase safe symbol, explicit bounded start/end, 5,000 result maximum, use_cache=False.
- Uses OpenBB provider's real QueryExecutor asynchronously, not arbitrary shell commands or broker APIs.
- No automatic provider installation, no secrets in Git or logs, no live trades, no remote service start. Isolated CI uses injected in-memory fake executor; actual authenticated FRED network call has NOT been run in this session.
- Source entries are strict, date-ordered and nonfinite/missing values are rejected. No silent zero-fill.
- to_prospective_causal_events makes all observations available only at the capture clock, and feeds our causal_stream_merge module.
- Original quote ZIP, private ledgers and credential material never enter the public GitHub repository.

Next: independent release vintage feed that retains first-seen timestamps; runner-level integration against M1, separate FRED auth harness, and full external worker/receipt acceptance. Keep PR Draft.
