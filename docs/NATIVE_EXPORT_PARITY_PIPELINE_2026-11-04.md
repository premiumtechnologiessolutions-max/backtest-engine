# Complete native-export -> NRFX parity construction path

Module: `src/norisk_quant/native_export_parity_pipeline.py`.

This **functioning pure-data integration** connects previously disconnected
vendor-shaped normalizers and the canonical NRFX cross-engine comparator.
For every planned external comparator in a frozen research blueprint, it:

1. Requires the pinned LEAN/Nautilus vendor commit identifier.
2. Requires complete local export bytes and exactly matching SHA256.
3. Requires the sidecar bytes and exactly matching SHA256.
4. Parses JSON strictly, rejecting duplicate fields, non-finite constants,
   unknown top-level schemas, oversized payloads and incomplete reports.
5. Converts LEAN `closedTrades` and a deliberate Nautilus positions-DataFrame
   JSON export into the existing 16-field normalized NRFX trade ledger.
6. Enforces USD-linear quantity, fees, timing and exact source-sidecar mapping
   through the existing source-shaped normalizers.
7. Runs comparison against the native NRFX ledger for *every* frozen engine,
   producing a bounded, deterministic, privacy-preserving mismatch report.

No broker, provider, external subprocess, original Gold archive or live market
data are accessed by the normalizer and synthetic tests.

**Crucial limitation:** a SHA256 over caller-provided export/sidecar bytes is
a strong accidental-corruption check but NOT proof those bytes came from a
real vendor process. A future trusted isolated subprocess supervisor must
produce independently signed launch/exit/source/sidecar evidence before any
claim of source authenticity. The status remains UNVERIFIED even on parity.

Inputs only support unambiguous one-instrument linear closed positions. Native
events with partial fills, intrabar ambiguity, multipliers, currency conversion,
netting and re-opened positions need a separate event-by-event adapter.
