# Vendor-neutral order lifecycle + fill allocation verifier

Functional code: `norisk_quant.vendor_order_lifecycle.verify_vendor_order_fill_lifecycles`.

This is the next construction-only accounting layer after closed-trade
and partial-fill reconciliation. For *every* frozen LEAN/Nautilus comparator,
a caller supplies a complete normalized order-event sequence and a
one-to-one mapping of existing fill IDs to order IDs. It verifies:

- Order submission before acknowledgement; no fills before ACK.
- Every fill belongs to exactly one known submitted order/trade/side/phase.
- Filled quantity never exceeds requested quantity, across partial fills.
- No fill after cancellation/rejection/full order completion.
- Every order reaches FILLED, CANCELLED or REJECTED by the close.
- Frozen quantity, direction, order type and limit price cannot mutate.
- BUY LIMIT fills cannot exceed their limit; SELL LIMIT fills cannot
  fall below their limit. Market orders have no artificial limit.
- Source sequence order and UTC timestamps, signal/close boundaries.
- Independent validation of every linked fill against the normalized
  trade ledger's VWAP, P&L, quantities and fixed USD/oz fee model.

Only MARKET and LIMIT orders are represented in V1. Stop/stop-limit/
trailing orders, busts, corrections, exchange sequence resets, multi-leg
positions and netting require explicit further engineering.

This verifier only knows caller-supplied synthetic/normalized events.
It does not prove a real LEAN/Nautilus executable, broker, or exchange
generated them. Its conclusion stays UNVERIFIED and it never starts
a strategy, market-data fetch, worker, or Gold backtest.
