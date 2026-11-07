# Vendor fill-event reconciliation — construction only

`src/norisk_quant/external_fill_event_reconciliation.py` adds a real
per-fill accounting audit to the existing LEAN/Nautilus source-shaped
trade-normalization and NRFX ledger-parity pipeline.

It requires every declared external vendor engine and every closed trade
to have a complete chronological series of fill events, including
partial entries/exits. It independently recomputes per-trade entry/exit
volume-weighted prices, roundtrip USD fees (owner's fixed 0.40 USD/oz),
gross P&L, net P&L and entry/exit timestamps. It refuses duplicate fills,
orphan trade identities, reversed or mixed directions, entry-after-exit,
missing fills, reversed chronology, invalid non-finite numbers and price
or fee discrepancies. It never averages a missing trade away.

A joint `normalize_compare_and_reconcile_vendor_fills` API runs the
existing native LEAN/Nautilus closed-position converters, NRFX row-parity
check, and this fill-stream audit in one pure-data pass.

**Acceptance boundary:** These events are supplied by the caller, not
proven to come from a real executable or broker. Even a perfect match is
UNVERIFIED. Event-source signatures, order-to-position lifecycle proof,
tick/quote provenance, full container sandbox, OOS statistical validation
and engine launch attestation remain mandatory later.

No Gold archive, market data provider, vendor executable or research
campaign was started. Tests contain invented synthetic prices only.
