"""FAC025: paired-quote entry audit for a BID-only canonical reference ledger.

Research diagnostic only. Does not authenticate caller receipts, reconstruct
tick fills, change the fixed $0.40/oz ALL-IN accounting, or certify returns.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import math
from numbers import Integral, Real
from statistics import median

import pandas as pd

from scripts.research_fac025_bidask_receipt import FIELDS

MINUTE = pd.Timedelta(minutes=1)
FEE = 0.40
MAX_M1 = 600_000
MAX_TRADES = 100_000
REQUIRED_TRADES = frozenset({
    "signal_at", "entry_at", "closed_at", "side", "entry_price",
    "ounces", "cost",
})


def _utc(value: object, label: str) -> pd.Timestamp:
    if not isinstance(value, datetime) or isinstance(value, str):
        raise ValueError(f"{label} must be an explicit UTC datetime")
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return stamp.tz_convert("UTC")


def _price(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return value


def audit_bid_reference_entry_quotes(paired_m1: list[dict],
                                     canonical_trades: pd.DataFrame) -> dict:
    """Check canonical BID-proxy entries against observed paired M1 opens.

    This explicitly does NOT reprice P/L. BUY ASK-vs-BID entry discrepancy
    and observed entry spread are diagnostics; adding them to the fixed
    all-in $0.40 would double-count unknown spread components.
    """
    if type(paired_m1) is not list or not 1 <= len(paired_m1) <= MAX_M1:
        raise ValueError("Paired M1 must be a bounded nonempty list")
    if (not isinstance(canonical_trades, pd.DataFrame)
            or not REQUIRED_TRADES.issubset(canonical_trades.columns)
            or len(canonical_trades) > MAX_TRADES):
        raise ValueError("Canonical trade ledger schema or size invalid")
    opens = {}
    previous = None
    gap_events = 0
    for row in paired_m1:
        if type(row) is not dict or row.keys() != FIELDS:
            raise ValueError("Malformed paired source M1")
        at = _utc(row["open_at"], "open_at")
        if at.value % 60_000_000_000:
            raise ValueError("Source M1 is not minute-aligned")
        if previous is not None:
            if at <= previous:
                raise ValueError("Source M1 must be strictly increasing and unique")
            if at - previous > MINUTE:
                gap_events += 1
        previous = at
        bid = {k: _price(row["bid_" + k], "bid_" + k)
               for k in ("open", "high", "low", "close")}
        ask = {k: _price(row["ask_" + k], "ask_" + k)
               for k in ("open", "high", "low", "close")}
        for side in (bid, ask):
            if not (side["low"] <= min(side["open"], side["close"])
                    and max(side["open"], side["close"]) <= side["high"]):
                raise ValueError("Invalid paired source OHLC")
        if any(ask[k] < bid[k] for k in bid):
            raise ValueError("Crossed paired BID/ASK OHLC")
        for key in ("bid_received_at", "ask_received_at"):
            if _utc(row[key], key) < at + MINUTE:
                raise ValueError("Complete source bar receipt precedes close")
        opens[at.value] = (bid["open"], ask["open"])

    spreads = []
    buy_discrepancies = []
    buy_count = 0
    previous_close = None
    for trade in canonical_trades.itertuples(index=False):
        signal = _utc(trade.signal_at, "signal_at")
        entry = _utc(trade.entry_at, "entry_at")
        closed = _utc(trade.closed_at, "closed_at")
        if (entry.value % 60_000_000_000 or entry <= signal
                or entry - signal > MINUTE or closed < entry):
            raise ValueError("Canonical entry chronology violates frozen 60s gate")
        if previous_close is not None and entry <= previous_close:
            raise ValueError("Canonical ledger violates one-slot capacity")
        previous_close = closed
        if isinstance(trade.side, bool) or not isinstance(trade.side, Integral) or trade.side not in (1, -1):
            raise ValueError("Invalid canonical trade side")
        entry_price = _price(trade.entry_price, "entry_price")
        ounces = _price(trade.ounces, "ounces")
        if (isinstance(trade.cost, bool) or not isinstance(trade.cost, Real)
                or not math.isfinite(float(trade.cost))
                or not math.isclose(float(trade.cost), FEE * ounces,
                                    rel_tol=0, abs_tol=1e-8)):
            raise ValueError("Canonical ledger changed fixed ALL-IN fee")
        if entry.value not in opens:
            raise ValueError("Canonical entry missing from observed paired M1")
        bid_open, ask_open = opens[entry.value]
        if not math.isclose(entry_price, bid_open, rel_tol=0, abs_tol=1e-8):
            raise ValueError("Canonical BID-reference entry is not observed BID open")
        spread = ask_open - bid_open
        spreads.append(spread)
        if trade.side == 1:
            buy_count += 1
            buy_discrepancies.append(spread)

    return {
        "status": "PAIRED_QUOTE_ENTRY_DIAGNOSTIC_ONLY_NOT_EXECUTABLE",
        "paired_m1_observed": len(paired_m1),
        "observed_m1_gap_events": gap_events,
        "canonical_reference_trades_audited": len(spreads),
        "buy_bid_proxy_entries": buy_count,
        "sell_bid_proxy_entries": len(spreads) - buy_count,
        "observed_entry_spread_median_usd_per_oz": median(spreads) if spreads else None,
        "observed_entry_spread_max_usd_per_oz": max(spreads) if spreads else None,
        "buy_entry_ask_minus_bid_max_usd_per_oz": (
            max(buy_discrepancies) if buy_discrepancies else None),
        "entry_spread_exceeds_fixed_fee_count": sum(s > FEE for s in spreads),
        "fixed_roundtrip_all_in_fee_usd_per_oz": FEE,
        "net_pnl_repriced": False,
        "monthly_pnl": "N/A",
        "floating_drawdown": "N/A",
        "source_authenticated": False,
        "paired_bidask_exit_fills_verified": False,
        "independent_oos_verified": False,
        "approved_strategies": 0,
    }
