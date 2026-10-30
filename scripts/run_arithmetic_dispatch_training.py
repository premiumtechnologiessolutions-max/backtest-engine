"""Execute a verified arithmetic generation on *exposed training years only*.

Requires a local authorized data archive and the original frozen training
input. Runs the canonical CLI twice (reference and fast), audits both output
trees, and publishes a batch atomically. Not an OOS or broker-fill certificate.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import pandas as pd

from norisk_quant.math_discovery import Formula
from scripts.materialize_arithmetic_generation import materialize, _load_strict

SCHEMA = "NRFX_ARITHMETIC_TRAINING_REPLAY_V1"
SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
SHA = re.compile(r"[0-9a-f]{64}\Z")
REPORTS = ("trades.csv", "monthly.csv", "weekly.csv", "equity_m1.csv",
           "gap_catalogue.csv")
SUMMARY_KEYS = (
    "trades", "net_pnl", "total_fees", "positive_months",
    "start_utc", "end_utc",
    "months_observed", "months_with_m1_observations",
    "max_drawdown_observed_m1", "last_observed_equity",
    "last_observed_realized_pnl", "accounting_checks",
    "forced_end_of_data_closures", "same_entry_bar_target_deferred",
    "trades_exposed_to_uncertain_gaps",
)
TRADE_FIELDS = (
    "strategy", "signal_at", "entry_at", "closed_at", "side",
    "entry_price", "exit_price", "stop", "target", "ounces",
    "gross_pnl", "cost", "net_pnl", "exit_reason", "gap_minutes",
)


def _digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_destination(path: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlink output path is forbidden")
    if path.exists():
        raise ValueError("Frozen replay destination already exists")


def _strict_formula(path: Path, expected: dict) -> None:
    source, digest = _load_strict(path)
    if digest != expected["file_sha256"] or type(source) is not dict:
        raise ValueError("Frozen dispatch formula SHA mismatch")
    formula = Formula(**source)
    if formula.identity() != expected["identity"]:
        raise ValueError("Frozen dispatch formula identity mismatch")


def _verify_trade_accounting(trades: pd.DataFrame) -> None:
    """Independent per-row accounting and chronology, even if both engines agree."""
    for row in trades.itertuples(index=False):
        if (row.side not in (-1, 1) or int(row.side) != row.side
                or row.gap_minutes < 0 or int(row.gap_minutes) != row.gap_minutes):
            raise ValueError("Invalid trade direction or gap minutes")
        numbers = (row.entry_price, row.exit_price, row.stop, row.target,
                   row.ounces, row.gross_pnl, row.cost, row.net_pnl)
        if not all(math.isfinite(float(value)) for value in numbers):
            raise ValueError("Nonfinite trade execution field")
        if (row.ounces <= 0 or min(row.entry_price, row.exit_price,
                                   row.stop, row.target) <= 0):
            raise ValueError("Invalid trade size or price")
        if ((row.side == 1 and not row.stop < row.entry_price < row.target)
                or (row.side == -1 and not row.target < row.entry_price < row.stop)):
            raise ValueError("Invalid protective stop/target geometry")
        gross = row.side * (row.exit_price - row.entry_price) * row.ounces
        if (abs(row.cost - 0.40 * row.ounces) > 1e-9
                or abs(row.gross_pnl - gross) > 1e-7
                or abs(row.net_pnl - (gross - row.cost)) > 1e-7):
            raise ValueError("Trade gross/net/fee arithmetic mismatch")
        stamps = [pd.Timestamp(value) for value in
                  (row.signal_at, row.entry_at, row.closed_at)]
        if (any(pd.isna(stamp) or stamp.tzinfo is None for stamp in stamps)
                or not stamps[0] <= stamps[1] <= stamps[2]):
            raise ValueError("Trade timestamps are not ordered timezone-aware UTC")
        if row.exit_reason in ("stop", "ambiguous_stop_first"):
            if abs(row.exit_price - row.stop) > 1e-7:
                raise ValueError("Trade stop exit differs from stop")
        elif row.exit_reason in ("target", "open_target"):
            if abs(row.exit_price - row.target) > 1e-7:
                raise ValueError("Trade target exit differs from target")
        elif row.exit_reason in ("open_stop", "gap_stop", "entry_open_beyond_stop"):
            if row.side * (row.exit_price - row.stop) > 1e-7:
                raise ValueError("Adverse open exit improved beyond stop")
        elif row.exit_reason not in ("end_of_data", "time_exit"):
            raise ValueError("Unknown trade exit reason")
        if any(stamp.second or stamp.microsecond or stamp.nanosecond
               for stamp in stamps):
            raise ValueError("Trade ledger contains non-M1-aligned timestamps")
    # The canonical executor allows one position only and explicitly forbids
    # a replacement on the minute another position exits. Reference/Fast
    # agreement alone cannot detect identical overlapping/corrupted ledgers.
    if len(trades) > 1:
        entries = pd.to_datetime(trades["entry_at"], utc=True, errors="raise")
        closes = pd.to_datetime(trades["closed_at"], utc=True, errors="raise")
        if (not entries.is_monotonic_increasing
                or not closes.is_monotonic_increasing):
            raise ValueError("Trade ledger is not in execution chronology")
        if any(next_entry <= prior_close
               for next_entry, prior_close in zip(entries.iloc[1:], closes.iloc[:-1])):
            raise ValueError("Trade ledger overlaps or re-enters on exit minute")


def _verify_monthly_booking(trades: pd.DataFrame, monthly: pd.DataFrame,
                            summary: dict, *, year: int) -> None:
    """Reconstruct each exit-booked UTC month from fills, not just annual sums.

    Reference/Fast agreement is insufficient when both reports share a
    misplaced trade or offsetting monthly edits. Empty months remain zero,
    never fabricated P/L, and all 12 training months must be represented.
    """
    required = ("period", "net_pnl", "total_cost", "trades", "wins")
    if monthly.columns.has_duplicates or not set(required).issubset(monthly.columns):
        raise ValueError("Monthly ledger missing required audit columns")
    periods = [f"{year}-{month:02d}" for month in range(1, 13)]
    if monthly["period"].tolist() != periods:
        raise ValueError("Monthly ledger missing, duplicated, or unordered UTC months")
    for field in required[1:]:
        values = monthly[field]
        if (not pd.api.types.is_numeric_dtype(values)
                or not all(math.isfinite(float(v)) for v in values)):
            raise ValueError(f"Monthly ledger invalid numeric field: {field}")
    for field in ("trades", "wins"):
        if any(value < 0 or int(value) != value for value in monthly[field]):
            raise ValueError(f"Monthly ledger invalid integer count: {field}")
    if any(monthly["wins"] > monthly["trades"]):
        raise ValueError("Monthly ledger wins exceed trades")
    if (type(summary.get("months_observed")) is not int
            or summary["months_observed"] != 12
            or type(summary.get("positive_months")) is not int
            or summary["positive_months"] != int((monthly["net_pnl"] > 0).sum())):
        raise ValueError("Monthly ledger disagrees with annual month summary")
    if len(trades):
        closes = pd.to_datetime(trades["closed_at"], utc=True, errors="raise")
        close_months = closes.dt.strftime("%Y-%m")
        if not close_months.isin(periods).all():
            raise ValueError("Monthly ledger has trade exits outside training year")
    else:
        close_months = pd.Series([], dtype="str")
    for month, row in zip(periods, monthly.itertuples(index=False)):
        booked = trades.loc[close_months == month]
        expected = {
            "trades": len(booked),
            "wins": int((booked["net_pnl"] > 0).sum()),
            "net_pnl": float(booked["net_pnl"].sum()),
            "total_cost": float(booked["cost"].sum()),
        }
        for field, value in expected.items():
            if abs(float(getattr(row, field)) - value) > 1e-7:
                raise ValueError(f"Monthly ledger exit-booking mismatch: {month} {field}")


def _verify_weekly_booking(trades: pd.DataFrame, weekly: pd.DataFrame,
                           summary: dict, *, year: int) -> None:
    """Reconstruct every UTC W-SUN exit bucket from the independent trade ledger.

    Agreement between engines and annual net totals does not prove weekly
    reports: equal-and-opposite edits to two weeks can otherwise pass.
    """
    required = ("period", "net_pnl", "total_cost", "trades", "wins")
    if weekly.columns.has_duplicates or not set(required).issubset(weekly.columns):
        raise ValueError("Weekly ledger missing required audit columns")
    try:
        start = pd.Timestamp(summary["start_utc"])
        end = pd.Timestamp(summary["end_utc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Weekly ledger requires valid UTC coverage bounds") from exc
    if (pd.isna(start) or pd.isna(end) or start.tzinfo is None
            or end.tzinfo is None):
        raise ValueError("Weekly ledger requires timezone-aware coverage bounds")
    start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
    if start > end or start.year != year or end.year != year:
        raise ValueError("Weekly ledger coverage outside requested training year")
    expected_periods = pd.period_range(
        start.tz_localize(None).to_period("W-SUN"),
        end.tz_localize(None).to_period("W-SUN"), freq="W-SUN")
    if weekly["period"].tolist() != [str(period) for period in expected_periods]:
        raise ValueError("Weekly ledger missing, duplicated, or unordered UTC weeks")
    for field in required[1:]:
        values = weekly[field]
        if (not pd.api.types.is_numeric_dtype(values)
                or not all(math.isfinite(float(value)) for value in values)):
            raise ValueError(f"Weekly ledger invalid numeric field: {field}")
    for field in ("trades", "wins"):
        if any(value < 0 or int(value) != value for value in weekly[field]):
            raise ValueError(f"Weekly ledger invalid integer count: {field}")
    if any(weekly["wins"] > weekly["trades"]):
        raise ValueError("Weekly ledger wins exceed trades")
    if len(trades):
        closes = pd.to_datetime(trades["closed_at"], utc=True, errors="raise")
        close_weeks = closes.dt.tz_localize(None).dt.to_period("W-SUN").astype(str)
        if not close_weeks.isin(weekly["period"]).all():
            raise ValueError("Weekly ledger missing trade exit week")
    else:
        close_weeks = pd.Series([], dtype="str")
    for week, row in zip(weekly["period"], weekly.itertuples(index=False)):
        booked = trades.loc[close_weeks == week]
        expected = {
            "trades": len(booked),
            "wins": int((booked["net_pnl"] > 0).sum()),
            "net_pnl": float(booked["net_pnl"].sum()),
            "total_cost": float(booked["cost"].sum()),
        }
        for field, value in expected.items():
            if abs(float(getattr(row, field)) - value) > 1e-7:
                raise ValueError(f"Weekly ledger exit-booking mismatch: {week} {field}")



def _verify_m1_equity(trades: pd.DataFrame, marks: pd.DataFrame,
                      summary: dict) -> None:
    """Rebuild observed minute-close equity risk and exit-booked realized P/L.

    Reference/Fast parity alone cannot detect identical corruption in both
    outputs. Never interpolate missing minutes or infer intrabar drawdown.
    """
    required = ("at", "realized_pnl", "floating_pnl", "equity", "drawdown")
    if marks.columns.has_duplicates or not set(required).issubset(marks.columns):
        raise ValueError("M1 equity missing required observed columns")
    if marks.empty:
        raise ValueError("M1 equity contains no observed minutes")
    try:
        timestamps = pd.to_datetime(marks["at"], utc=True, errors="raise")
        raw_times = [pd.Timestamp(value) for value in marks["at"]]
        bounds = [pd.Timestamp(summary[name]) for name in ("start_utc", "end_utc")]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("M1 equity invalid UTC observation timestamps") from exc
    if (any(pd.isna(t) or t.tzinfo is None for t in raw_times + bounds)
            or timestamps.duplicated().any() or not timestamps.is_monotonic_increasing
            or any(t.second or t.microsecond or t.nanosecond for t in timestamps)
            or timestamps.iloc[0] != bounds[0].tz_convert("UTC")
            or timestamps.iloc[-1] != bounds[1].tz_convert("UTC")):
        raise ValueError("M1 equity unordered, duplicated or mismatched UTC coverage")
    for field in required[1:]:
        values = marks[field]
        if (not pd.api.types.is_numeric_dtype(values)
                or not all(math.isfinite(float(value)) for value in values)):
            raise ValueError(f"M1 equity invalid numeric field: {field}")
    if ((marks["equity"] - marks["realized_pnl"]
         - marks["floating_pnl"]).abs() > 1e-7).any():
        raise ValueError("M1 equity realized/floating reconciliation mismatch")
    expected_dd = (marks["equity"].cummax().clip(lower=0)
                   - marks["equity"]).clip(lower=0)
    if (marks["drawdown"] - expected_dd).abs().gt(1e-7).any():
        raise ValueError("M1 equity observed drawdown differs from reconstructed peaks")
    if (abs(float(summary["max_drawdown_observed_m1"]) - float(expected_dd.max())) > 1e-7
            or abs(float(summary["last_observed_equity"]) - float(marks["equity"].iloc[-1])) > 1e-7
            or abs(float(summary["last_observed_realized_pnl"])
                   - float(marks["realized_pnl"].iloc[-1])) > 1e-7):
        raise ValueError("M1 equity summary disagrees with observed marks")
    if int(timestamps.dt.strftime("%Y-%m").nunique()) != 12:
        raise ValueError("M1 equity missing observed training month")
    if len(trades):
        closes = pd.to_datetime(trades["closed_at"], utc=True, errors="raise")
        entries = pd.to_datetime(trades["entry_at"], utc=True, errors="raise")
        signals = pd.to_datetime(trades["signal_at"], utc=True, errors="raise")
        # Arithmetic M1 signals are confirmed at the END of an observed
        # source candle. Its open is confirmation minus one minute. The
        # confirmation instant itself need not be an observed M1 open:
        # the final candle before a quote gap can legitimately close at the
        # first missing minute. Never accept a signal with no source candle.
        signal_source_opens = signals - pd.Timedelta(minutes=1)
        if not signal_source_opens.isin(timestamps).all():
            raise ValueError("M1 equity missing observed signal source bar")
        # A canonical M1 fill requires an observed source bar at its entry
        # minute. Bounds-only checks accept fabricated fills inside quote gaps.
        if (not closes.isin(timestamps).all()
                or not entries.isin(timestamps).all()
                or (entries < timestamps.iloc[0]).any()
                or (closes > timestamps.iloc[-1]).any()):
            raise ValueError("M1 equity missing observed trade close or entry coverage")
        # At each observed minute close, a position is open only after its
        # entry minute and strictly before its exit minute. The executor
        # books exits before recording that minute's equity mark. Rebuild
        # flat exposure from fills so matching engines cannot invent
        # floating P/L (and thereby distort drawdown) while no trade exists.
        active = (pd.DatetimeIndex(entries).searchsorted(timestamps, side="right")
                  - pd.DatetimeIndex(closes).searchsorted(timestamps, side="right"))
        if (active < 0).any() or (active > 1).any():
            raise ValueError("M1 equity trade occupancy violates one-position execution")
        if (abs(marks["floating_pnl"].to_numpy(dtype=float)[active == 0]) > 1e-7).any():
            raise ValueError("M1 equity has nonzero floating P/L while flat")
        booked = trades.groupby(closes)["net_pnl"].sum().reindex(
            pd.DatetimeIndex(timestamps), fill_value=0.0)
    else:
        if marks["floating_pnl"].abs().gt(1e-7).any():
            raise ValueError("M1 equity has floating P/L without any trade")
        booked = pd.Series(0.0, index=pd.DatetimeIndex(timestamps))
    expected_realized = booked.cumsum().to_numpy(dtype=float)
    if any(abs(float(actual) - float(expected)) > 1e-7
           for actual, expected in zip(marks["realized_pnl"], expected_realized)):
        raise ValueError("M1 equity realized timeline disagrees with trade exits")


def _compare_outputs(reference: Path, fast: Path, *, identity: str, year: int) -> dict:
    """Fail on any differing execution field, report bucket, or M1 equity mark."""
    summaries = []
    for engine, directory in (("reference", reference), ("fast", fast)):
        summary, _ = _load_strict(directory / "summary.json")
        if type(summary) is not dict:
            raise ValueError("Invalid execution summary")
        params = summary.get("run_parameters", {})
        if (type(params) is not dict or params.get("execution") != engine
                or params.get("strategy") != "arithmetic"
                or params.get("timeframe") != "M1"
                or params.get("arithmetic_formula_sha256") != identity
                or params.get("all_in_cost_per_ounce") != 0.40
                or params.get("ounces") != 1.0):
            raise ValueError("Unexpected or mismatched canonical CLI parameters")
        fingerprints = summary.get("source_fingerprints")
        fingerprint = (fingerprints.get("loaded_m1_bidask_sha256")
                       if type(fingerprints) is dict else None)
        if type(fingerprint) is not str or SHA.fullmatch(fingerprint) is None:
            raise ValueError("Missing or invalid loaded M1 Bid/Ask SHA256 fingerprint")
        # The canonical report writes the literal string PASSED, not an
        # arbitrary object. Reference/Fast agreement on FAILED is not proof.
        if summary.get("accounting_checks") != "PASSED":
            raise ValueError("Canonical execution accounting was not PASSED")
        trade_count = summary.get("trades")
        if type(trade_count) is not int or trade_count < 0:
            raise ValueError("Invalid canonical summary trade count")
        for count_name in ("forced_end_of_data_closures",
                           "same_entry_bar_target_deferred",
                           "trades_exposed_to_uncertain_gaps"):
            count = summary.get(count_name)
            if type(count) is not int or not 0 <= count <= trade_count:
                raise ValueError(f"Invalid canonical summary count: {count_name}")
        if (type(summary.get("months_with_m1_observations")) is not int
                or summary["months_with_m1_observations"] != 12):
            raise ValueError("Annual training sample omits an observed calendar month")
        summaries.append(summary)
    # Both invocations must share the entire execution contract apart from
    # the deliberately selected engine. Comparing only selected fields could
    # certify runs with divergent optional CLI settings.
    left_params = dict(summaries[0]["run_parameters"])
    right_params = dict(summaries[1]["run_parameters"])
    left_params.pop("execution")
    right_params.pop("execution")
    if left_params != right_params:
        raise ValueError("Reference/Fast run parameters differ")
    if summaries[0]["source_fingerprints"] != summaries[1]["source_fingerprints"]:
        raise ValueError("Reference/Fast source fingerprints differ")
    for key in SUMMARY_KEYS:
        if summaries[0].get(key) != summaries[1].get(key):
            raise ValueError(f"Reference/Fast summary mismatch: {key}")
    for filename in REPORTS:
        left = pd.read_csv(reference / filename)
        right = pd.read_csv(fast / filename)
        if filename == "trades.csv":
            for frame in (left, right):
                if frame.columns.has_duplicates or not set(TRADE_FIELDS).issubset(frame.columns):
                    raise ValueError("Trade ledger missing 15 execution audit fields")
        try:
            pd.testing.assert_frame_equal(
                left, right, check_dtype=False, check_exact=False,
                atol=1e-7, rtol=0, check_like=False,
            )
        except AssertionError as exc:
            raise ValueError(f"Reference/Fast {filename} mismatch") from exc
    trades = pd.read_csv(reference / "trades.csv")
    # The 15-field ledger must belong to the frozen candidate itself, not
    # another strategy with identical fills and copied summary metadata.
    if len(trades) and (trades["strategy"] != f"arithmetic_{identity[:16]}").any():
        raise ValueError("Trade strategy identity mismatch")
    summary = summaries[0]
    _verify_trade_accounting(trades)
    _verify_m1_equity(trades, pd.read_csv(reference / "equity_m1.csv"), summary)
    _verify_monthly_booking(trades, pd.read_csv(reference / "monthly.csv"),
                            summary, year=year)
    _verify_weekly_booking(trades, pd.read_csv(reference / "weekly.csv"),
                           summary, year=year)
    if summary["trades"] != len(trades):
        raise ValueError("Trade count differs from persisted ledger")
    if len(trades):
        for field in ("net_pnl", "cost", "ounces"):
            if not pd.to_numeric(trades[field], errors="coerce").notna().all():
                raise ValueError(f"Invalid trade accounting field: {field}")
        fees = (trades["ounces"] * 0.40).sum()
        if abs(float(trades["cost"].sum()) - float(fees)) > 1e-7:
            raise ValueError("Noncanonical per-trade fee")
        net = float(trades["net_pnl"].sum())
    else:
        fees = net = 0.0
    if (abs(float(summary["total_fees"]) - float(fees)) > 1e-7
            or abs(float(summary["net_pnl"]) - net) > 1e-7):
        raise ValueError("Trade/summary accounting mismatch")
    for filename in ("monthly.csv", "weekly.csv"):
        buckets = pd.read_csv(reference / filename)
        if abs(float(buckets["net_pnl"].sum()) - net) > 1e-7:
            raise ValueError(f"Trade/{filename} accounting mismatch")
    return {"trades": len(trades), "net_usd_per_oz": net,
            "fees_usd": float(fees), "positive_months": summary["positive_months"],
            "bidask_sha256": summaries[0]["source_fingerprints"]["loaded_m1_bidask_sha256"]}


def execute(training_input: Path, generation_manifest: Path,
            dispatch_dir: Path, data: Path, source_sha256: str,
            year: int, destination: Path, *, start_ordinal: int = 1,
            limit: int = 8) -> dict:
    """No holdout access: selected year must be in frozen TRAINING years."""
    if (type(year) is not int or type(start_ordinal) is not int
            or type(limit) is not int or start_ordinal < 1
            or not 1 <= limit <= 128 or type(source_sha256) is not str
            or SHA.fullmatch(source_sha256) is None):
        raise ValueError("Invalid bounded frozen training replay controls")
    if source_sha256 != SOURCE_SHA:
        raise ValueError("Only the preregistered original Gold ZIP SHA is permitted")
    _safe_destination(destination)
    if not data.is_file() or data.suffix.lower() != ".zip":
        raise ValueError("A local original source ZIP is required")
    if _digest(data) != source_sha256:
        raise ValueError("Original source ZIP SHA mismatch")
    # Replays generation from the ORIGINAL training input, never trusts an
    # isolated self-reported dispatch index or a changed formula JSON.
    dispatch = materialize(training_input, generation_manifest, dispatch_dir)
    if year not in dispatch["training_years"]:
        raise ValueError("Year is not in frozen training; holdout replay forbidden")
    entries = dispatch["formulas"]
    if start_ordinal > len(entries):
        raise ValueError("Requested ordinal exceeds frozen generation")
    selected = entries[start_ordinal - 1:start_ordinal - 1 + limit]
    for row in selected:
        _strict_formula(dispatch_dir / row["relative_path"], row)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _safe_destination(destination)
    staging = Path(tempfile.mkdtemp(prefix=".nrfx_arithmetic_training_",
                                    dir=destination.parent))
    try:
        records = []
        for row in selected:
            name = f"{row['ordinal']:03d}_{row['identity'][:16]}"
            formula_path = dispatch_dir / row["relative_path"]
            outputs = {}
            for engine in ("reference", "fast"):
                target = staging / name / engine
                command = [
                    sys.executable, "-m", "norisk_quant.cli", "backtest",
                    "--data", str(data), "--start", f"{year}-01-01",
                    "--end", f"{year}-12-31", "--out", str(target),
                    "--strategy", "arithmetic", "--timeframe", "M1",
                    "--formula-json", str(formula_path), "--execution", engine,
                    "--ounces", "1", "--all-in-cost-per-ounce", "0.40",
                ]
                subprocess.run(command, check=True, capture_output=True,
                               text=True)
                outputs[engine] = target
            metrics = _compare_outputs(outputs["reference"], outputs["fast"],
                                       identity=row["identity"], year=year)
            records.append({"ordinal": row["ordinal"], "identity": row["identity"],
                            "reference_fast_parity": "PASSED",
                            "metrics": metrics, "relative_dir": name})
        if _digest(data) != source_sha256:
            raise ValueError("Original source ZIP changed during replay")
        # Refuse to publish if source evidence or any formula changed mid-run.
        if materialize(training_input, generation_manifest, dispatch_dir) != dispatch:
            raise ValueError("Frozen dispatch changed during replay")
        for row in selected:
            _strict_formula(dispatch_dir / row["relative_path"], row)
        index = {
            "schema": SCHEMA, "training_only": True,
            "independent_oos_proven": False, "live_trading_authorized": False,
            "data_archive_sha256": source_sha256,
            "training_input_sha256": dispatch["training_input_sha256"],
            "generation_manifest_sha256": dispatch["generation_manifest_sha256"],
            "year": year, "requested_start_ordinal": start_ordinal,
            "requested_limit": limit, "completed": len(records),
            "all_in_cost_per_ounce": 0.40, "results": records,
        }
        (staging / "training_replay_index.json").write_text(
            json.dumps(index, sort_keys=True, indent=2, allow_nan=False) + "\n",
            encoding="utf-8")
        _safe_destination(destination)
        os.replace(staging, destination)
        return index
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("training-input", "generation-manifest", "dispatch-dir",
                 "data", "data-sha256", "year", "out"):
        parser.add_argument("--" + name, required=True,
                            type=int if name == "year" else
                            str if name == "data-sha256" else Path)
    parser.add_argument("--start-ordinal", type=int, default=1)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv)
    result = execute(args.training_input, args.generation_manifest,
                     args.dispatch_dir, args.data, args.data_sha256,
                     args.year, args.out, start_ordinal=args.start_ordinal,
                     limit=args.limit)
    print(json.dumps({"completed": result["completed"], "year": result["year"],
                      "status": "TRAINING_ONLY_PARITY_VERIFIED"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
