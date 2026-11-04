# Native output mapping: LEAN ClosedTrade + NautilusTrader positions

This is **functional pure-data normalization**, not external-engine execution.
Code: src/norisk_quant/upstream_trade_normalizers.py

The LEAN branch maps documented JSON closedTrades fields:
id, symbols, entryTime, exitTime, direction (0=LONG,1=SHORT),
quantity, entryPrice, exitPrice, profitLoss, totalFees.
It enforces an exact USD-linear contract with a fixed 0.40 USD/oz fee.

The NautilusTrader branch maps its documented positions DataFrame:
position_id index, instrument_id, strategy_id, entry, side, quantity,
peak_qty, avg_px_open, avg_px_close, commissions, realized_pnl,
ts_opened, ts_closed and is_snapshot. It only supports closed FLAT
non-snapshot, simple linear one-ounce/USD positions and exact USD
commissions. NETTING/reopened/partially filled cycles require
event-level proof and are deliberately refused.

Native reports lack our frozen signal identity, stop/target or exit
reasons. A sidecar with exactly these fields plus a pinned SHA256 is
mandatory; it cannot override native entry/exit prices, P/L or fees.
A sidecar checksum alone does not prove it was frozen before the study.

Outputs use the 16-field NRFX reference ledger schema, which now feeds
cross_engine_parity.compare_frozen_engine_ledgers for real row-level
price/time/fee comparison. This is usable with **synthetic** source-shaped
fixtures today; actual LEAN/Nautilus runner integration remains pending.

Native documents consulted:
https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/trades
https://nautilustrader.io/docs/latest/concepts/reports/
https://nautilustrader.io/docs/latest/concepts/positions/

Vendor source pins come from the Git submodules in this repository.
These normalizers do not import vendor code, assert upstream execution,
open Gold archives, call AI services, run subprocesses, accept trading
signals or claim source/authenticated portfolio parity.