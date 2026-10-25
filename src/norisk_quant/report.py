from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .execution import Result
from .model import Settings


def _periods(trades: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, period: str) -> pd.DataFrame:
    first = start.tz_convert("UTC").tz_localize(None).to_period(period)
    last = end.tz_convert("UTC").tz_localize(None).to_period(period)
    intervals = pd.period_range(first, last, freq=period)
    if trades.empty:
        group = pd.DataFrame(index=intervals)
    else:
        local = trades.copy()
        local["period"] = (
            pd.to_datetime(local["closed_at"], utc=True)
            .dt.tz_localize(None)
            .dt.to_period(period)
        )
        group = local.groupby("period").agg(
            trades=("net_pnl", "size"),
            wins=("net_pnl", lambda x: (x > 0).sum()),
            gross_profit=("net_pnl", lambda x: x[x > 0].sum()),
            gross_loss=("net_pnl", lambda x: x[x < 0].sum()),
            net_pnl=("net_pnl", "sum"),
            total_cost=("cost", "sum"),
        )
    group = group.reindex(intervals, fill_value=0)
    for name in ("trades", "wins", "gross_profit", "gross_loss", "net_pnl", "total_cost"):
        if name not in group:
            group[name] = 0
    group["losses_or_breakeven"] = group["trades"] - group["wins"]
    group["win_rate"] = group["wins"] / group["trades"].where(group["trades"] > 0)
    group["profit_factor"] = (
        group["gross_profit"]
        / (-group["gross_loss"]).where(group["gross_loss"] < 0)
    )
    group.index.name = "period"
    return group


def report(result: Result, settings: Settings, out: str | Path, *, source: str = "unknown") -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    equity = result.equity.copy()
    trades = result.trades.copy()
    start, end = equity.index[0], equity.index[-1]
    monthly = _periods(trades, start, end, "M")
    weekly = _periods(trades, start, end, "W-SUN")
    peak = equity["equity"].cummax().clip(lower=0)
    equity["drawdown"] = (peak - equity["equity"]).clip(lower=0)
    month_end_equity = equity["equity"].resample("ME").last()
    month_end_dd = (
        month_end_equity.cummax().clip(lower=0) - month_end_equity
    ).clip(lower=0)
    monthly["month_end_equity"] = month_end_equity.to_numpy()
    monthly["month_end_drawdown"] = month_end_dd.to_numpy()

    total_profit = float(trades.loc[trades["net_pnl"] > 0, "net_pnl"].sum())
    total_loss = float(trades.loc[trades["net_pnl"] < 0, "net_pnl"].sum())
    wins = int((trades["net_pnl"] > 0).sum()) if not trades.empty else 0
    summary = {
        "engine": "noriskfx-quant-engine/0.1.0",
        "execution": "synthetic_same_reference_bid_ohlc_fixed_all_in_fee",
        "data_source": source,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "settings": asdict(settings),
        "trades": int(len(trades)),
        "wins": wins,
        "win_rate": wins / len(trades) if len(trades) else None,
        "net_pnl": float(trades["net_pnl"].sum()),
        "total_fees": float(trades["cost"].sum()),
        "profit_factor": total_profit / -total_loss if total_loss < 0 else None,
        "max_drawdown_observed_m1": float(equity["drawdown"].max()),
        "max_drawdown_month_end": float(month_end_dd.max()),
        "positive_months": int((monthly["net_pnl"] > 0).sum()),
        "nonpositive_months": int((monthly["net_pnl"] <= 0).sum()),
        "months_observed": int(len(monthly)),
        "open_equity_warning": "M1 OHLC cannot reconstruct the tick path or floating equity during missing intervals.",
        "incomplete_final_period_warning": "Final month can be partial. end_of_data exits are synthetic research liquidations.",
    }
    trades.to_csv(out / "trades.csv", index=False)
    equity.to_csv(out / "equity_m1.csv")
    monthly.to_csv(out / "monthly.csv")
    weekly.to_csv(out / "weekly.csv")
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
