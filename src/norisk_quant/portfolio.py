"""Shared-capacity multi-strategy M1 OHLC research execution.

Not a broker margin model. Positions share an observed M1 clock, capital
capacity and a single realized/floating equity ledger. No tick-path inference.
The only trading cost is the fixed ALL-IN USD 0.40 per ounce per roundtrip.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .model import Signal


@dataclass(frozen=True)
class PortfolioSettings:
    ounces_by_strategy: Mapping[str, float]
    max_open_positions: int = 3
    max_total_ounces: float = 3.0
    max_entry_delay_minutes: int = 1
    close_at_end: bool = True
    all_in_cost_per_ounce: float = 0.40

    def __post_init__(self) -> None:
        if not self.ounces_by_strategy or any(
            not name or not math.isfinite(float(qty)) or qty <= 0
            for name, qty in self.ounces_by_strategy.items()
        ):
            raise ValueError("Each strategy needs a finite positive ounce allocation")
        if self.max_open_positions < 1 or not math.isfinite(self.max_total_ounces) or self.max_total_ounces <= 0:
            raise ValueError("Invalid shared portfolio capacity")
        if self.max_entry_delay_minutes < 0:
            raise ValueError("Negative signal entry delay")
        if self.all_in_cost_per_ounce != 0.40:
            raise ValueError("Research contract fixes ALL-IN fee at $0.40/oz per roundtrip")


@dataclass
class PortfolioResult:
    trades: pd.DataFrame
    equity: pd.DataFrame
    pending_at_end: int
    expired_signals: int
    capacity_rejected: int
    duplicate_strategy_rejected: int
    open_positions_at_end: int


@dataclass
class _OpenPosition:
    signal_at: pd.Timestamp
    entry_at: pd.Timestamp
    strategy: str
    side: int
    ounces: float
    entry_price: float
    stop: float
    target: float
    gap_minutes: int = 0


def run_portfolio(
    minutes: pd.DataFrame, signals: Sequence[Signal], settings: PortfolioSettings
) -> PortfolioResult:
    """Deterministic shared-capacity replay; no intraminute same-slot recycling.

    Signals are eligible only after their confirmation timestamp. At most one
    open position per strategy. At a given minute, open-capacity is frozen at
    the START of the minute: a trade stopped this minute does not release a
    slot until the next observed M1 bar. Ties use (confirmation, strategy,
    input order) priority, not hindsight profitability.
    """
    if minutes.empty or not isinstance(minutes.index, pd.DatetimeIndex):
        raise ValueError("Nonempty M1 DatetimeIndex required")
    if minutes.index.tz is None or minutes.index.has_duplicates or not minutes.index.is_monotonic_increasing:
        raise ValueError("M1 index must be timezone-aware, sorted and unique")
    if not {"o", "h", "l", "c"}.issubset(minutes):
        raise ValueError("M1 OHLC required")
    if (minutes.index.asi8 % 60_000_000_000 != 0).any():
        raise ValueError("M1 timestamps must align to whole minutes")
    o, h, l, c = (minutes[col].to_numpy(dtype=float) for col in ("o", "h", "l", "c"))
    if not all(np.isfinite(x).all() for x in (o, h, l, c)) or (l <= 0).any() or (l > np.minimum(o,c)).any() or (h < np.maximum(o,c)).any():
        raise ValueError("Invalid source M1 OHLC")

    ordered = []
    for i, sig in enumerate(signals):
        if sig.strategy not in settings.ounces_by_strategy:
            raise ValueError(f"Missing allocation for {sig.strategy!r}")
        confirmed = pd.Timestamp(sig.confirmed_at)
        if confirmed.tzinfo is None:
            raise ValueError("Signal timestamp must be timezone-aware")
        if not math.isfinite(sig.stop_distance) or not math.isfinite(sig.target_distance):
            raise ValueError("Signal distances must be finite")
        ordered.append((confirmed.tz_convert("UTC"), sig.strategy, i, sig))
    ordered.sort(key=lambda row: row[:3])

    positions: dict[str, _OpenPosition] = {}
    pointer = expired = rejected_capacity = rejected_duplicate = 0
    realized = 0.0
    trades: list[dict] = []
    equity: list[dict] = []
    prev: pd.Timestamp | None = None

    def exit_position(p: _OpenPosition, at: pd.Timestamp, price: float, reason: str) -> None:
        nonlocal realized
        gross = p.side * (price - p.entry_price) * p.ounces
        fee = p.ounces * settings.all_in_cost_per_ounce
        net = gross - fee
        realized += net
        trades.append({
            "strategy": p.strategy, "signal_at": p.signal_at,
            "entry_at": p.entry_at, "closed_at": at, "side": p.side,
            "entry_price": p.entry_price, "exit_price": price,
            "stop": p.stop, "target": p.target, "ounces": p.ounces,
            "gross_pnl": gross, "cost": fee, "net_pnl": net,
            "exit_reason": reason, "gap_minutes": p.gap_minutes,
        })
        del positions[p.strategy]

    for i, when in enumerate(minutes.index):
        at = pd.Timestamp(when).tz_convert("UTC")
        op, hi, lo, cl = float(o[i]), float(h[i]), float(l[i]), float(c[i])
        missing = max(0, round((at - prev).total_seconds() / 60) - 1) if prev is not None else 0
        prev = at
        # Capacity is frozen BEFORE any exits on this minute.
        occupied_names = set(positions)
        slots = settings.max_open_positions - len(positions)
        available_ounces = settings.max_total_ounces - sum(p.ounces for p in positions.values())

        # Existing positions first: adverse gap-through at first observable open.
        for p in list(positions.values()):
            p.gap_minutes += missing
            if (p.side == 1 and op <= p.stop) or (p.side == -1 and op >= p.stop):
                exit_position(p, at, op, "gap_stop" if missing else "open_stop")
            elif (p.side == 1 and op >= p.target) or (p.side == -1 and op <= p.target):
                exit_position(p, at, p.target, "open_target")

        # Consume all signals already confirmed at this observed M1 open.
        while pointer < len(ordered) and ordered[pointer][0] <= at:
            confirmed, name, _, sig = ordered[pointer]
            pointer += 1
            if (at - confirmed).total_seconds() / 60 > settings.max_entry_delay_minutes:
                expired += 1
                continue
            if name in occupied_names or name in positions:
                rejected_duplicate += 1
                continue
            qty = float(settings.ounces_by_strategy[name])
            if slots <= 0 or qty > available_ounces + 1e-12:
                rejected_capacity += 1
                continue
            slots -= 1
            available_ounces -= qty
            positions[name] = _OpenPosition(
                signal_at=confirmed, entry_at=at, strategy=name,
                side=sig.side, ounces=qty, entry_price=op,
                stop=op - sig.side * sig.stop_distance,
                target=op + sig.side * sig.target_distance,
            )

        # Conservative OHLC ambiguity for ALL still-open positions.
        for p in list(positions.values()):
            stop_hit = lo <= p.stop if p.side == 1 else hi >= p.stop
            target_hit = hi >= p.target if p.side == 1 else lo <= p.target
            if stop_hit:
                exit_position(p, at, p.stop, "ambiguous_stop_first" if target_hit else "stop")
            elif target_hit:
                exit_position(p, at, p.target, "target")

        floating = sum(
            p.side * (cl - p.entry_price) * p.ounces
            - p.ounces * settings.all_in_cost_per_ounce
            for p in positions.values()
        )
        equity.append({
            "at": at, "realized_pnl": realized, "floating_pnl": floating,
            "equity": realized + floating,
            "open_positions": len(positions),
            "gross_open_ounces": sum(p.ounces for p in positions.values()),
        })

    open_at_end = len(positions)
    if positions and settings.close_at_end:
        at = pd.Timestamp(minutes.index[-1]).tz_convert("UTC")
        for p in list(positions.values()):
            exit_position(p, at, float(c[-1]), "end_of_data")
        equity[-1].update(realized_pnl=realized, floating_pnl=0.0,
                          equity=realized, open_positions=0, gross_open_ounces=0.0)

    columns = [
        "strategy", "signal_at", "entry_at", "closed_at", "side",
        "entry_price", "exit_price", "stop", "target", "ounces",
        "gross_pnl", "cost", "net_pnl", "exit_reason", "gap_minutes",
    ]
    return PortfolioResult(
        trades=pd.DataFrame.from_records(trades, columns=columns),
        equity=pd.DataFrame.from_records(equity).set_index("at"),
        pending_at_end=len(ordered) - pointer,
        expired_signals=expired,
        capacity_rejected=rejected_capacity,
        duplicate_strategy_rejected=rejected_duplicate,
        open_positions_at_end=open_at_end,
    )


def validate_portfolio(result: PortfolioResult, settings: PortfolioSettings, *, atol: float = 1e-7) -> dict:
    """Validate fee, shared exposure, realized P/L timeline, and per-strategy overlap."""
    eq, tr = result.equity, result.trades
    if eq.empty or eq.index.has_duplicates or not eq.index.is_monotonic_increasing:
        raise ValueError("Invalid equity time axis")
    if not {"realized_pnl", "floating_pnl", "equity", "open_positions", "gross_open_ounces"}.issubset(eq):
        raise ValueError("Missing portfolio equity/exposure columns")
    vals = eq[["realized_pnl", "floating_pnl", "equity", "open_positions", "gross_open_ounces"]].to_numpy(dtype=float)
    if not np.isfinite(vals).all() or not np.allclose(vals[:,0] + vals[:,1], vals[:,2], rtol=0, atol=atol):
        raise ValueError("Invalid portfolio equity arithmetic")
    if (vals[:,3] < 0).any() or (vals[:,3] > settings.max_open_positions).any() or (vals[:,4] < 0).any() or (vals[:,4] > settings.max_total_ounces + atol).any():
        raise ValueError("Portfolio capacity exceeded")
    if tr.empty:
        booked = pd.Series(0.0, index=eq.index)
    else:
        if not tr["strategy"].isin(settings.ounces_by_strategy).all():
            raise ValueError("Unknown strategy in portfolio trade ledger")
        expected_qty = tr["strategy"].map(settings.ounces_by_strategy).to_numpy(dtype=float)
        quantities = tr["ounces"].to_numpy(dtype=float)
        fees = tr["cost"].to_numpy(dtype=float)
        gross = tr["gross_pnl"].to_numpy(dtype=float)
        net = tr["net_pnl"].to_numpy(dtype=float)
        expected_gross = tr["side"].to_numpy(dtype=float) * (
            tr["exit_price"].to_numpy(dtype=float) - tr["entry_price"].to_numpy(dtype=float)
        ) * quantities
        if not all(np.isfinite(x).all() for x in (quantities, fees, gross, net)):
            raise ValueError("Invalid portfolio trade amounts")
        if not np.allclose(quantities, expected_qty, rtol=0, atol=atol):
            raise ValueError("Portfolio quantity mismatch")
        if not np.allclose(fees, quantities * 0.40, rtol=0, atol=atol):
            raise ValueError("Double counted fee or variable fee")
        if not np.allclose(gross, expected_gross, rtol=0, atol=atol) or not np.allclose(net, gross - fees, rtol=0, atol=atol):
            raise ValueError("Portfolio P/L mismatch")
        entry = pd.to_datetime(tr["entry_at"], utc=True)
        closed = pd.to_datetime(tr["closed_at"], utc=True)
        confirmed = pd.to_datetime(tr["signal_at"], utc=True)
        if (entry < confirmed).any() or (closed < entry).any() or not closed.isin(eq.index).all():
            raise ValueError("Portfolio time causality mismatch")
        for _, group in tr.assign(_entry=entry, _exit=closed).groupby("strategy"):
            group = group.sort_values("_entry")
            if (group["_entry"].iloc[1:].to_numpy() <= group["_exit"].iloc[:-1].to_numpy()).any():
                raise ValueError("Same-strategy overlap or same-minute reentry")
        booked = tr.groupby(closed)["net_pnl"].sum().reindex(eq.index, fill_value=0.0)
    if not np.allclose(eq["realized_pnl"].to_numpy(), booked.cumsum().to_numpy(), rtol=0, atol=atol):
        raise ValueError("Portfolio realized P/L chronology mismatch")
    return {"status": "PASSED", "trades": int(len(tr)),
            "net_pnl_closed": float(tr["net_pnl"].sum()) if len(tr) else 0.0,
            "max_observed_open_positions": int(eq["open_positions"].max()),
            "max_observed_open_ounces": float(eq["gross_open_ounces"].max()),
            "cost_model": "FIXED_ALL_IN_0.40_PER_OUNCE_PER_ROUNDTRIP"}


def write_portfolio_report(result: PortfolioResult, settings: PortfolioSettings, out: str | Path) -> dict:
    """Write shared realized and marked-to-market weekly/monthly research ledgers."""
    audit = validate_portfolio(result, settings)
    dest = Path(out)
    dest.mkdir(parents=True, exist_ok=True)
    eq = result.equity
    tr = result.trades
    start = eq.index[0].tz_convert("UTC").tz_localize(None)
    end = eq.index[-1].tz_convert("UTC").tz_localize(None)
    for label, freq, rule in (("monthly", "M", "ME"), ("weekly", "W-SUN", "W-SUN")):
        periods = pd.period_range(start.to_period(freq), end.to_period(freq), freq=freq)
        if tr.empty:
            realized = pd.DataFrame(index=periods)
        else:
            df = tr.copy()
            df["period"] = pd.to_datetime(df["closed_at"], utc=True).dt.tz_localize(None).dt.to_period(freq)
            realized = df.groupby("period").agg(trades=("net_pnl", "size"), net_pnl=("net_pnl", "sum"), cost=("cost", "sum"))
        realized = realized.reindex(periods, fill_value=0.0)
        for col in ("trades", "net_pnl", "cost"):
            if col not in realized: realized[col] = 0.0
        raw_marked = eq["equity"].resample(rule).last()
        # Missing calendar periods have no observable closing quote. Carry
        # forward the last observed mark, and explicitly flag the absence.
        marked = raw_marked.ffill()
        realized["has_observed_m1"] = raw_marked.notna().to_numpy()
        realized["period_end_equity"] = marked.to_numpy()
        realized["equity_change"] = marked.diff().fillna(marked.iloc[0]).to_numpy()
        realized.index.name = "period"
        realized.to_csv(dest / f"{label}.csv")
    eq.to_csv(dest / "equity_m1.csv")
    tr.to_csv(dest / "trades.csv", index=False)
    peak = eq["equity"].cummax().clip(lower=0)
    summary = {**audit,
        "fixed_all_in_usd_per_ounce": 0.40,
        "max_open_positions_allowed": settings.max_open_positions,
        "max_total_ounces_allowed": settings.max_total_ounces,
        "max_observed_m1_close_drawdown": float((peak - eq["equity"]).max()),
        "pending_at_end": result.pending_at_end,
        "expired_signals": result.expired_signals,
        "capacity_rejected": result.capacity_rejected,
        "duplicate_strategy_rejected": result.duplicate_strategy_rejected,
        "open_positions_before_optional_end_close": result.open_positions_at_end,
        "caveat": "Synthetic M1 OHLC with stop-first; not broker ticks or a broker margin model. Missing calendar periods carry the last observed equity with has_observed_m1=false; this is NOT an observed month-end quote.",
    }
    (dest / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
