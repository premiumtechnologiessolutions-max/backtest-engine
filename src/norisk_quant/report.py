from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .execution import Result
from .accounting import validate_execution
from .gaps import annotate_trade_gap_exposure, classify_index_gaps
from .model import Settings


def _atomic_private_write(path: Path, writer) -> None:
    """Atomically replace a report using a fresh 0600 temporary file.

    Even if the caller has a normal 022 umask, raw private trades/quotes
    must never have a world-readable intermediate state. The temp file
    is fsynced before replacement; re-runs cannot follow planted symlinks.
    Existing hardlinks are also forbidden to prevent ambiguous originals.
    """
    path = Path(path)
    if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
        raise ValueError("Unsafe report destination")
    fd, staging = tempfile.mkstemp(prefix=".nrfx-report-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
            raise ValueError("Unsafe report destination during publish")
        os.replace(staging, path)
        if os.name == "posix":
            dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


def _private_csv(frame: pd.DataFrame, path: Path, *, index: bool) -> None:
    _atomic_private_write(path, lambda handle: frame.to_csv(handle, index=index))


def _private_json(value: dict, path: Path) -> None:
    _atomic_private_write(
        path,
        lambda handle: handle.write(json.dumps(value, ensure_ascii=False, indent=2)),
    )


def _marked_periods(equity: pd.Series, rule: str) -> pd.DataFrame:
    """Observed marks only; never allocate a cross-gap change to a period.

    An empty calendar period has no defensible closing mark. The first mark
    after it is also insufficient to allocate the intervening P/L by period.
    Keep those changes unknown and expose the cross-gap difference separately.
    """
    marked = equity.resample(rule).last()
    samples = equity.resample(rule).count()
    change = marked.diff()
    change.iloc[0] = marked.iloc[0]  # Initial research equity is zero.
    resumed = samples.gt(0) & samples.shift(1, fill_value=1).eq(0)
    since_observed = marked - marked.ffill().shift(1)
    since_observed.iloc[0] = marked.iloc[0]
    return pd.DataFrame({
        "period_end_equity": marked,
        "equity_change": change,
        "observed_m1_samples": samples,
        "has_observations": samples.gt(0),
        "has_observed_m1": samples.gt(0),
        "change_spans_unobserved_period": resumed,
        "change_since_last_observed_period": since_observed,
    })


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


def report(result: Result, settings: Settings, out: str | Path, *, source: str = "unknown", provenance: dict | None = None, run_parameters: dict | None = None) -> dict:
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
    month_marks = _marked_periods(equity["equity"], "ME")
    month_end_equity = month_marks["period_end_equity"]
    month_end_dd = (
        month_end_equity.cummax().clip(lower=0) - month_end_equity
    ).clip(lower=0)
    monthly["month_end_equity"] = month_end_equity.to_numpy()
    monthly["month_end_drawdown"] = month_end_dd.to_numpy()
    # Unrealized equity must be visible separately from P/L booked at exit.
    # First period uses a starting research equity of zero.
    monthly["month_equity_change"] = month_marks["equity_change"].to_numpy()
    week_marks = _marked_periods(equity["equity"], "W-SUN")
    week_end_equity = week_marks["period_end_equity"]
    weekly["week_end_equity"] = week_end_equity.to_numpy()
    weekly["week_equity_change"] = week_marks["equity_change"].to_numpy()
    monthly["month_has_observed_m1"] = month_marks["has_observations"].to_numpy()
    weekly["week_has_observed_m1"] = week_marks["has_observations"].to_numpy()
    for periods, marks in ((monthly, month_marks), (weekly, week_marks)):
        for column in ("observed_m1_samples", "has_observations", "has_observed_m1",
                       "change_spans_unobserved_period",
                       "change_since_last_observed_period"):
            periods[column] = marks[column].to_numpy()

    total_profit = float(trades.loc[trades["net_pnl"] > 0, "net_pnl"].sum())
    total_loss = float(trades.loc[trades["net_pnl"] < 0, "net_pnl"].sum())
    wins = int((trades["net_pnl"] > 0).sum()) if not trades.empty else 0
    summary = {
        "engine": "noriskfx-quant-engine/0.1.0",
        "execution": "synthetic_same_reference_bid_ohlc_fixed_all_in_fee",
        "data_source": source,
        "source_fingerprints": provenance or {},
        "run_parameters": run_parameters or {},
        "reproducibility_warning": (
            "M1 slice SHA-256 verifies input quote bytes and timestamps, but "
            "exact computational reproducibility also requires an immutable "
            "Git commit and locked dependency versions. This is synthetic OHLC "
            "research execution, not broker tick-fill validation."
        ),
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "settings": asdict(settings),
        "trades": int(len(trades)),
        "accounting_checks": audit["accounting_checks"],
        "forced_end_of_data_closures": audit["forced_end_of_data_closures"],
        "same_entry_bar_target_deferred": result.uncertain_entry_tp_deferred,
        "same_entry_bar_target_note": "M1 OHLC cannot prove target occurred after limit fill; target is deferred when both occur in entry M1.",
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
        "months_with_m1_observations": int(month_marks["has_observations"].sum()),
        "calendar_months_without_m1": int((~month_marks["has_observations"]).sum()),
        "weeks_without_m1_observations": int((~week_marks["has_observations"]).sum()),
        "period_coverage_note": (
            "Period-end equity is the last observed M1 close within that period. "
            "Empty periods and the next period's allocated equity change are unknown; "
            "change_since_last_observed_period records the cross-gap difference "
            "without assigning it to an unobserved period."
        ),
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
    _private_csv(gaps, out / "gap_catalogue.csv", index=False)
    _private_csv(trades, out / "trades.csv", index=False)
    _private_csv(equity, out / "equity_m1.csv", index=True)
    _private_csv(monthly, out / "monthly.csv", index=True)
    _private_csv(weekly, out / "weekly.csv", index=True)
    _private_json(summary, out / "summary.json")
    return summary
