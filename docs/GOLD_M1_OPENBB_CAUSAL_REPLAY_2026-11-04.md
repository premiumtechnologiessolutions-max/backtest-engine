# Gold M1 + OpenBB causal research timeline (2026-11-04)

This is an integrated, read-only and bounded **real NRFX engine-data adapter**:
`gold_macro_replay.py` calls the existing `validate_loaded_m1` and
`fingerprint_loaded_m1`, converts precisely validated M1 BID/ASK OHLC into
closed-candle events, reads the frozen snapshot from the actual upstream
OpenBB/FRED adapter, and merges it via `causal_stream_merge`.

Critical causal semantics:
- Gold M1 source timestamps are candle **opens**. Full 8-field OHLC is not
  available until at least **open + 1 minute**. This is an optimistic
  research-only earliest boundary, not a broker fill guarantee.
- OpenBB/FRED `FredSeries` drops realtime vintage fields. Observation
  **period date** is retained as `event_at_ns`, but **availability is the
  snapshot capture timestamp**, not a fictitious old release clock. Thus a
  2026 snapshot is invisible to any 2012/2017/2020/2024 historical decision.
- No calendar gap-filling, resampling, zeroing of nonfinite values or price
  adjustment. A source-mismatched fingerprint causes failure, although a
  self-computed digest is NOT original-data provider authentication.
- Research inputs are bounded to 50,000 M1 candles per call, suitable for
  deterministic research chunks. A full multi-year engine requires a
  separately audited chunked coordinator and source reconciliation.
- `research_state_at` is a diagnostic only, with explicit
  `live_trading_authorized=False`, no provider result approval, and no
  historical FRED release proof.

Tests use synthetic M1 and FRED rows. No raw ZIP, FRED token, quote history,
broker trading orders or credentials enter this Git repository. The provider's
live authenticated FRED request and actual source 13-field replay are NOT
certified by these tests. The full repository GitHub CI is required to accept
this software integration.

Research only; never use this module for live trading.
