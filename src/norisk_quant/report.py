from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .execution import Result
from .accounting import validate_execution
from .gaps import annotate_trade_gap_exposure, classify_index_gaps
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
    audit = validate_execution(result, settings)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    equity = result.equity.copy()
    gaps = classify_index_gaps(equity.index, min_missing_minutes=10)
    trades = annotate_trade_gap_exposure(result.trades, gaps)
    start, end = equity.index[0], equity.index[-1]
    monthly = _periods(trades, start, end, "M")
    weekly = _periods(trades, start, end, "W-SUN")
    # Post-trade labels. These flags NEVER affect signals or fills.
    if not trades.empty:
        flagged = trades.loc[trades["gap_execution_review_required"]]
        if not flagged.empty:
            for periods, freq in ((monthly, "M"), (weekly, "W-SUN")):
                labels = (
                    pd.to_datetime(flagged["closed_at"], utc=True)
                    .dt.tz_localize(None).dt.to_period(freq)
                )
                counts = flagged.groupby(labels).size()
                pnl = flagged.groupby(labels)["net_pnl"].sum()
                periods["uncertain_gap_trades"] = counts.reindex(periods.index, fill_value=0).astype(int)
                periods["uncertain_gap_trades_net_pnl"] = pnl.reindex(periods.index, fill_value=0.0)
    for periods in (monthly, weekly):
        if "uncertain_gap_trades" not in periods:
            periods["uncertain_gap_trades"] = 0
            periods["uncertain_gap_trades_net_pnl"] = 0.0
    peak = equity["equity"].cummax().clip(lower=0)
    equity["drawdown"] = (peak - equity["equity"]).clip(lower=0)
    month_end_equity = equity["equity"].resample("ME").last()
    month_end_dd = (
        month_end_equity.cummax().clip(lower=0) - month_end_equity
    ).clip(lower=0)
    monthly["month_end_equity"] = month_end_equity.to_numpy()
    monthly["month_end_drawdown"] = month_end_dd.to_numpy()
    # Unrealized equity must be visible separately from P/L booked at exit.
    # First period uses a starting research equity of zero.
    monthly["month_equity_change"] = month_end_equity.diff().fillna(
        month_end_equity.iloc[0]
    ).to_numpy()
    week_end_equity = equity["equity"].resample("W-SUN").last()
    weekly["week_end_equity"] = week_end_equity.to_numpy()
    weekly["week_equity_change"] = week_end_equity.diff().fillna(
        week_end_equity.iloc[0]
    ).to_numpy()

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
        "accounting_checks": audit["accounting_checks"],
        "forced_end_of_data_closures": audit["forced_end_of_data_closures"],
        "forced_end_of_data_pnl": audit["forced_end_of_data_pnl"],
        "forced_liquidation_caveat": (
            "end_of_data is an artificial research close, not an observed broker liquidation."
        ),
        "wins": wins,
        "win_rate": wins / len(trades) if len(trades) else None,
        "net_pnl": float(trades["net_pnl"].sum()),
        "total_fees": float(trades["cost"].sum()),
        "gaps_over10_missing_minutes": int(len(gaps)),
        "gaps_needing_manual_review": int(gaps["needs_review"].sum()),
        "trades_exposed_to_uncertain_gaps": int(trades["gap_execution_review_required"].sum()),
        "net_pnl_from_trades_exposed_to_uncertain_gaps": float(
            trades.loc[trades["gap_execution_review_required"], "net_pnl"].sum()
        ),
        "gap_classification_note": (
            "Classifies timestamp patterns only. Holiday hints and unusual gaps "
            "require independent broker/provider evidence, and OHLC cannot reconstruct "
            "missing quotes or true execution."
        ),
        "profit_factor": total_profit / -total_loss if total_loss < 0 else None,
        "max_drawdown_observed_m1": float(equity["drawdown"].max()),
        "max_drawdown_month_end": float(month_end_dd.max()),
        "last_observed_equity": float(equity["equity"].iloc[-1]),
        "last_observed_realized_pnl": float(equity["realized_pnl"].iloc[-1]),
        "monthly_mtm_vs_realized_note": (
            "monthly.net_pnl recognizes trades at EXIT; month_equity_change "
            "uses observed minute-close equity including floating P/L and accrued fee."
        ),
        "positive_months": int((monthly["net_pnl"] > 0).sum()),
        "nonpositive_months": int((monthly["net_pnl"] <= 0).sum()),
        "months_observed": int(len(monthly)),
        "open_equity_warning": "M1 OHLC cannot reconstruct the tick path or floating equity during missing intervals.",
        "incomplete_final_period_warning": "Final month can be partial. end_of_data exits are synthetic research liquidations.",
    }
    if not trades.empty:
        forced = trades[trades["exit_reason"] == "end_of_data"]
        if not forced.empty:
            end_labels = pd.to_datetime(forced["closed_at"], utc=True).dt.tz_localize(None).dt.to_period("M")
            end_count = forced.groupby(end_labels).size()
            end_pnl = forced.groupby(end_labels)["net_pnl"].sum()
            monthly["synthetic_end_of_data_trades"] = end_count.reindex(monthly.index, fill_value=0).astype(int)
            monthly["synthetic_end_of_data_net_pnl"] = end_pnl.reindex(monthly.index, fill_value=0.0)
    if "synthetic_end_of_data_trades" not in monthly:
        monthly["synthetic_end_of_data_trades"] = 0
        monthly["synthetic_end_of_data_net_pnl"] = 0.0
    gaps.to_csv(out / "gap_catalogue.csv", index=False)
    trades.to_csv(out / "trades.csv", index=False)
    equity.to_csv(out / "equity_m1.csv")
    monthly.to_csv(out / "monthly.csv")
    weekly.to_csv(out / "weekly.csv")
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
