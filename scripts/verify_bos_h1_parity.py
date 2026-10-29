"""Compare the ACTUAL GitHub engine against independent archived gold trade ledgers.

Requires separately authorized private original Gold data.zip and the archived
standalone research results. Raw XAUUSD data must NOT be committed to GitHub.

Example:
  python scripts/verify_bos_h1_parity.py \
    --gold-zip "/secure/Gold data.zip" \
    --reference-root "/secure/nrf_bos_h1_validation" \
    --years 2012 2013 2014 2015 2016 2017 2018 2019 \
    --out "/secure/reports/bos_h1_parity.json"

For security, never download arbitrary inputs or execute anything from ZIP.
The original market-data archive is read as annual JSON only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from norisk_quant.bos_fib import BosFibSettings, bos_fib_limit_orders
from norisk_quant.data import load_market
from norisk_quant.h1_regime import filter_orders_h1
from norisk_quant.limit_engine import run_limits
from norisk_quant.model import Settings
from norisk_quant.source_exit_integrity import verify_source_open_exit_prices


EXPECTED_MARKET_SHA256 = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
FIELDS = {
    "signal_at": "signal_time",
    "entry_at": "entry_time",
    "closed_at": "exit_time",
    "side": "side",
    "entry_price": "entry",
    "exit_price": "exit",
    "stop": "stop",
    "target": "target",
    "gross_pnl": "gross",
    "cost": "fee",
    "net_pnl": "net",
    "exit_reason": "exit_reason",
    "gap_minutes": "gap_minutes",
}
TIMES = {"signal_at", "entry_at", "closed_at"}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for buf in iter(lambda: file.read(8 * 1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()



def read_reference_csv(path: Path, *, required_columns: set[str]) -> pd.DataFrame:
    """Read archived replay CSV without pandas' silent header repair.

    Reject duplicate/missing headers, ragged rows, malformed CSV and symlinks.
    This checks transport/schema integrity, not the truth of executions.
    """
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Archived reference CSV must be an existing regular file, not a symlink")
    try:
        # Parse and validate the SAME in-memory snapshot; a second read of
        # path could otherwise ingest different bytes after validation.
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            snapshot = handle.read()
        reader = csv.reader(io.StringIO(snapshot, newline=""), strict=True)
        header = next(reader, None)
        if not header or any(not name for name in header):
            raise ValueError("Archived reference CSV has missing or empty header")
        if len(set(header)) != len(header):
            raise ValueError("Archived reference CSV has duplicate header names")
        missing = required_columns - set(header)
        if missing:
            raise ValueError(f"Archived reference CSV missing required fields: {sorted(missing)}")
        for row in reader:
            if len(row) != len(header):
                raise ValueError(
                    f"Archived reference CSV row has {len(row)} fields; "
                    f"expected {len(header)} (line {reader.line_num})"
                )
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("Archived reference CSV is malformed or not UTF-8") from exc
    return pd.read_csv(io.StringIO(snapshot))


def exact_ledger_check(ours: pd.DataFrame, reference: pd.DataFrame) -> dict:
    if len(ours) != len(reference):
        raise AssertionError(
            f"Trade count mismatch: actual={len(ours)} archived={len(reference)}"
        )
    # Even zero-trade scenarios must prove the full reference schema exists.
    # Otherwise a truncated/empty CSV could silently pass replay acceptance.
    for current, expected in FIELDS.items():
        if current not in ours or expected not in reference:
            raise AssertionError(f"Missing ledger field {current}/{expected}")
    if ours.empty:
        return {"trades": 0, "fields": len(FIELDS), "max_abs_pnl_delta": 0.0}
    for current, expected in FIELDS.items():
        if current in TIMES:
            # Archived timestamps are integral Unix seconds. Flooring current
            # nanoseconds would incorrectly accept subsecond execution drift.
            # Neither side may silently coerce timestamps: utc=True on a
            # naive engine timestamp assumes UTC, and dtype=int64 on an
            # archived fractional Unix second truncates the fraction.
            actual_values = ours[current].tolist()
            archived_values = reference[expected].tolist()
            if any(
                not isinstance(value, datetime)
                or pd.isna(value)
                or value.tzinfo is None
                for value in actual_values
            ):
                raise AssertionError(
                    f"First differing field: {current} (invalid or naive timestamp)"
                )
            if any(
                isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, np.integer))
                for value in archived_values
            ):
                raise AssertionError(
                    f"First differing field: {current} (archived Unix seconds must be integers)"
                )
            lhs_ns = pd.to_datetime(ours[current], utc=True).dt.as_unit("ns").astype("int64").to_numpy()
            rhs_seconds = np.asarray(archived_values, dtype="int64")
            equals = bool(
                np.all(lhs_ns % 1_000_000_000 == 0)
                and np.array_equal(lhs_ns // 1_000_000_000, rhs_seconds)
            )
        elif current == "exit_reason":
            # dtype=str would turn numeric reason codes into text, allowing
            # invalid schema values to masquerade as matching exit labels.
            actual_reasons = ours[current].tolist()
            archived_reasons = reference[expected].tolist()
            if not all(isinstance(value, str) and value for value in
                       actual_reasons + archived_reasons):
                raise AssertionError(
                    "First differing field: exit_reason (expected nonempty text)"
                )
            equals = actual_reasons == archived_reasons
        elif current in {"side", "gap_minutes"}:
            # np.array_equal(True, 1) and np.array_equal(1.0, 1) are True.
            # A 13-field *exact* replay must reject boolean/floating values
            # masquerading as the discrete side and gap-minute fields.
            def strict_values(series: pd.Series) -> list[int]:
                values = series.tolist()
                if any(
                    isinstance(value, (bool, np.bool_))
                    or not isinstance(value, (int, np.integer))
                    for value in values
                ):
                    raise AssertionError(
                        f"First differing field: {current} (not a strict integer)"
                    )
                if current == "side" and any(value not in (-1, 1) for value in values):
                    raise AssertionError(f"First differing field: {current} (invalid side)")
                if current == "gap_minutes" and any(value < 0 for value in values):
                    raise AssertionError(f"First differing field: {current} (negative gap)")
                return values

            equals = strict_values(ours[current]) == strict_values(reference[expected])
        else:
            # to_numpy(dtype=float) would silently turn True into 1.0 and
            # numeric-looking strings into prices/P&L. Both are schema drift
            # even if the resulting numbers happen to match.
            for series in (ours[current], reference[expected]):
                if (not pd.api.types.is_numeric_dtype(series.dtype)
                        or pd.api.types.is_bool_dtype(series.dtype)):
                    raise AssertionError(
                        f"First differing field: {current} (invalid numeric dtype)"
                    )
            # np.allclose(inf, inf) is True. Nonfinite prices, fees or P/L
            # must never certify a supposedly exact historical replay.
            try:
                actual_numbers = ours[current].to_numpy(dtype=float)
                archived_numbers = reference[expected].to_numpy(dtype=float)
            except (TypeError, ValueError) as exc:
                raise AssertionError(
                    f"First differing field: {current} (nonnumeric value)"
                ) from exc
            if not (
                np.isfinite(actual_numbers).all()
                and np.isfinite(archived_numbers).all()
            ):
                raise AssertionError(
                    f"First differing field: {current} (nonfinite value)"
                )
            equals = np.allclose(
                actual_numbers, archived_numbers, rtol=0, atol=1e-7,
            )
        if not equals:
            raise AssertionError(f"First differing field: {current}")
    # Matching corrupt ledgers are not proof of valid execution.  Check
    # independent physical/accounting invariants on BOTH sides, after the
    # 13-field comparison has established the schema and finite values.
    for label, ledger, fields in (
        ("engine", ours, {
            "signal": "signal_at", "entry_time": "entry_at",
            "exit_time": "closed_at", "entry": "entry_price",
            "exit": "exit_price", "stop": "stop", "target": "target",
            "fee": "cost", "gross": "gross_pnl", "net": "net_pnl",
            "exit_reason": "exit_reason",
        }),
        ("archive", reference, {
            "signal": "signal_time", "entry_time": "entry_time",
            "exit_time": "exit_time", "entry": "entry",
            "exit": "exit", "stop": "stop", "target": "target",
            "fee": "fee", "gross": "gross", "net": "net",
            "exit_reason": "exit_reason",
        }),
    ):
        def times(key: str) -> np.ndarray:
            values = ledger[fields[key]]
            if label == "engine":
                return pd.to_datetime(values, utc=True).dt.as_unit("ns").astype("int64").to_numpy()
            return values.to_numpy(dtype="int64") * 1_000_000_000

        signal_ns, entry_ns, exit_ns = times("signal"), times("entry_time"), times("exit_time")
        if np.any(entry_ns < signal_ns) or np.any(exit_ns < entry_ns):
            raise AssertionError(f"Ledger invariant: {label} signal/entry/exit chronology")
        for price in ("entry", "exit", "stop", "target"):
            if np.any(ledger[fields[price]].to_numpy(dtype=float) <= 0):
                raise AssertionError(f"Ledger invariant: {label} nonpositive {price} price")
        fee = ledger[fields["fee"]].to_numpy(dtype=float)
        gross = ledger[fields["gross"]].to_numpy(dtype=float)
        net = ledger[fields["net"]].to_numpy(dtype=float)
        if not np.allclose(fee, 0.40, rtol=0, atol=1e-9):
            raise AssertionError(f"Ledger invariant: {label} fee differs from fixed $0.40/oz")
        if not np.allclose(net, gross - fee, rtol=0, atol=1e-7):
            raise AssertionError(f"Ledger invariant: {label} net != gross - fee")
        # The frozen reference replays exactly ONE ounce. Two equally
        # corrupted ledgers could otherwise match all 13 fields and agree
        # that net == gross - fee while reporting a fabricated gross P/L.
        side = ledger["side"].to_numpy(dtype=np.int64)
        entry = ledger[fields["entry"]].to_numpy(dtype=float)
        exit_price = ledger[fields["exit"]].to_numpy(dtype=float)
        expected_gross = side * (exit_price - entry)
        if not np.allclose(gross, expected_gross, rtol=0, atol=1e-7):
            raise AssertionError(
                f"Ledger invariant: {label} gross != side * (exit - entry) * 1oz"
            )
        stop = ledger[fields["stop"]].to_numpy(dtype=float)
        target = ledger[fields["target"]].to_numpy(dtype=float)
        if np.any(((side == 1) & ~((stop < entry) & (entry < target)))
                  | ((side == -1) & ~((target < entry) & (entry < stop)))):
            raise AssertionError(
                f"Ledger invariant: {label} invalid directional stop/target geometry"
            )
        # Identical reference/engine rows can still fabricate an exit reason.
        # The limit executor always fills stop/target at the configured bound,
        # except an adverse opening gap/first quote can worsen a stop.
        # End-of-data closes at the last observed market close.
        reasons = ledger[fields["exit_reason"]].tolist()
        fixed_stop_reasons = {"stop", "ambiguous_stop_first"}
        fixed_target_reasons = {"target", "open_target"}
        adverse_open_reasons = {"gap_stop", "open_stop", "entry_open_beyond_stop"}
        allowed_reasons = (
            fixed_stop_reasons | fixed_target_reasons
            | adverse_open_reasons | {"end_of_data"}
        )
        if any(reason not in allowed_reasons for reason in reasons):
            raise AssertionError(
                f"Ledger invariant: {label} unknown exit reason"
            )
        stop_mask = np.asarray([reason in fixed_stop_reasons for reason in reasons])
        target_mask = np.asarray([reason in fixed_target_reasons for reason in reasons])
        adverse_mask = np.asarray([reason in adverse_open_reasons for reason in reasons])
        exit_price = ledger[fields["exit"]].to_numpy(dtype=float)
        if not np.allclose(exit_price[stop_mask], stop[stop_mask], rtol=0, atol=1e-7):
            raise AssertionError(
                f"Ledger invariant: {label} stop exit price differs from stop"
            )
        if not np.allclose(exit_price[target_mask], target[target_mask], rtol=0, atol=1e-7):
            raise AssertionError(
                f"Ledger invariant: {label} target exit price differs from target"
            )
        # A long's adverse stop-open fill cannot exceed its stop; a short's
        # cannot be below its stop.  Never upgrade an opening gap to a
        # favorable fill while preserving a misleading stop exit label.
        if np.any(side[adverse_mask] * (exit_price[adverse_mask] - stop[adverse_mask]) > 1e-7):
            raise AssertionError(
                f"Ledger invariant: {label} favorable price on adverse open stop"
            )
    return {
        "trades": len(ours),
        "fields": len(FIELDS),
        "max_abs_pnl_delta": float(
            np.max(
                np.abs(
                    ours["net_pnl"].to_numpy(dtype=float)
                    - reference["net"].to_numpy(dtype=float)
                )
            )
        ),
    }



def validate_replay_market_year(m1: pd.DataFrame, year: int) -> None:
    """Require a valid UTC M1 calendar-year scope before replay certification.

    Month presence is necessary but not sufficient for a complete market
    history: weekends, broker closures, and missing minutes need separate
    source-quality assessment. This prevents a truncated annual source from
    being certified solely because its archived trade ledger also truncates.
    """
    index = m1.index
    if (
        not isinstance(index, pd.DatetimeIndex)
        or index.empty
        or index.tz is None
        or str(index.tz) != "UTC"
        or index.hasnans
        or index.has_duplicates
        or not index.is_monotonic_increasing
    ):
        raise ValueError("Historical replay requires nonempty sorted unique UTC M1 timestamps")
    if (index.year != year).any():
        raise ValueError(f"Historical replay M1 includes timestamps outside {year}")
    missing = sorted(set(range(1, 13)) - set(index.month.tolist()))
    if missing:
        raise ValueError(
            f"Historical replay year {year} omits calendar months: {missing}; "
            "cannot certify a full annual source replay"
        )



def validate_end_of_data_source_close(m1: pd.DataFrame, trades: pd.DataFrame) -> int:
    """Cross-check forced final exits against the ACTUAL final observed BID close.

    Exact 13-field agreement between two ledgers cannot certify a fabricated
    end_of_data price or timestamp if both ledgers share the same mistake.
    The one-position limit executor can force at most one final exit.
    This is M1 source-consistency, NOT real broker/tick execution proof.
    """
    if "exit_reason" not in trades.columns:
        raise AssertionError("End-of-data source check requires exit_reason")
    forced = trades.loc[trades["exit_reason"] == "end_of_data"]
    if forced.empty:
        return 0
    if len(forced) != 1:
        raise AssertionError("End-of-data source check found multiple forced final exits")
    if (
        m1.empty or not isinstance(m1.index, pd.DatetimeIndex)
        or m1.index.tz is None or "c" not in m1.columns
    ):
        raise AssertionError("End-of-data source check requires final UTC M1 BID close")
    final_at = pd.Timestamp(m1.index[-1]).tz_convert("UTC")
    row = forced.iloc[0]
    closed = row["closed_at"]
    if (
        not isinstance(closed, datetime) or closed.tzinfo is None
        or pd.Timestamp(closed).tz_convert("UTC") != final_at
    ):
        raise AssertionError("End-of-data exit timestamp differs from last observed M1")
    try:
        observed_close = float(m1["c"].iloc[-1])
        exit_price = float(row["exit_price"])
    except (TypeError, ValueError) as exc:
        raise AssertionError("End-of-data exit/source close is not numeric") from exc
    if not (
        np.isfinite(observed_close) and np.isfinite(exit_price)
        and np.isclose(exit_price, observed_close, rtol=0, atol=1e-7)
    ):
        raise AssertionError("End-of-data exit price differs from final observed M1 BID close")
    return 1


def validate_replay_years(years: list[int]) -> None:
    """Never report PASSED when no scenarios were requested or years repeat."""
    if not isinstance(years, (list, tuple)) or not years:
        raise ValueError("Select at least one archived calendar year")
    if any(
        isinstance(year, (bool, np.bool_))
        or not isinstance(year, (int, np.integer))
        or not 2010 <= year <= 2026
        for year in years
    ):
        raise ValueError("Replay years must be integer calendar years 2010–2026")
    if len(years) != len(set(years)):
        raise ValueError("Duplicate replay years would double-count scenarios")



def validate_reference_summary_row(row: pd.Series) -> tuple[int, int, float]:
    """Reject archived yearly.csv counts that would be silently truncated.

    int(689.9), int(True), and int("689") all succeed in Python but must
    never certify a 13-field source replay. Annual net must also be finite,
    native numeric data rather than a string or boolean.
    """
    counts = []
    for name in ("trades", "orders"):
        value = row[name]
        if (
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer))
            or value < 0
        ):
            raise AssertionError(
                f"Archived yearly summary {name} must be a nonnegative integer"
            )
        counts.append(int(value))
    if counts[0] > counts[1]:
        raise AssertionError("Archived yearly summary trades exceed orders")
    net = row["net_usd_oz"]
    if (
        isinstance(net, (bool, np.bool_))
        or not isinstance(net, (int, float, np.integer, np.floating))
        or not np.isfinite(net)
    ):
        raise AssertionError("Archived yearly summary net_usd_oz must be finite numeric")
    return counts[0], counts[1], float(net)


def verify(gold_zip: Path, reference_root: Path, years: list[int]) -> dict:
    validate_replay_years(years)
    sha = file_sha256(gold_zip)
    if sha != EXPECTED_MARKET_SHA256:
        raise ValueError("Dataset SHA-256 differs from archived reference gold source")
    yearly = read_reference_csv(
        reference_root / "yearly.csv",
        required_columns={"year", "variant", "trades", "orders", "net_usd_oz"},
    )
    complete = []
    for year in years:
        # Read annual JSON only and don't allow unseen feed replacement.
        m1 = load_market(gold_zip, f"{year}-01-01", f"{year}-12-31")
        validate_replay_market_year(m1, year)
        setups = bos_fib_limit_orders(m1, settings=BosFibSettings())
        h1_aligned = filter_orders_h1(m1, setups)
        variants = {
            "h1_only": h1_aligned,
            "h1_and_5x": [
                o for o in h1_aligned
                if abs(o.target - o.price) >= 5 * 0.40 - 1e-10
            ],
        }
        for name, orders in variants.items():
            result = run_limits(m1, orders, Settings(
                ounces=1.0, roundtrip_cost_per_ounce=0.40,
            ))
            source_open_exits_verified = verify_source_open_exit_prices(m1, result.trades)
            baseline = read_reference_csv(
                reference_root / "results" / str(year) / name / "trades.csv",
                required_columns=set(FIELDS.values()),
            )
            check = exact_ledger_check(result.trades, baseline)
            final_source_closes = validate_end_of_data_source_close(m1, result.trades)
            summary_row = yearly.loc[
                (yearly["year"] == year) & (yearly["variant"] == name)
            ]
            if len(summary_row) != 1:
                raise AssertionError("Missing or duplicate year/variant reference")
            expected_count, expected_orders, expected_net = validate_reference_summary_row(
                summary_row.iloc[0]
            )
            if len(orders) != expected_orders or check["trades"] != expected_count:
                raise AssertionError("Signal count or trade count does not reconcile")
            total = float(result.trades["net_pnl"].sum())
            if not np.isclose(total, expected_net, rtol=0, atol=1e-6):
                raise AssertionError("Annual P/L fails standalone reference reconciliation")
            complete.append({
                "year": year,
                "variant": name,
                "M1_rows": len(m1),
                "signals": len(orders),
                "net_usd_1oz": total,
                "deferred_same_entry_bar_TP": result.uncertain_entry_tp_deferred,
                "end_of_data_source_closes_verified": final_source_closes,
                "source_open_stop_exits_verified": source_open_exits_verified,
                **check,
                "status": "PASSED",
            })
    # Re-check the original ZIP after every requested year/variant was read.
    # Without this, an archive replaced after the initial SHA verification
    # could yield a PASSED report falsely attributed to the frozen source.
    # This detects persistent mutation, not adversarial swap-and-restore races.
    if file_sha256(gold_zip) != sha:
        raise ValueError("Dataset archive changed during historical replay")
    return {
        "status": "PASSED",
        "source_sha256": sha,
        "market": "XAUUSD synthetic BID-reference research",
        "execution_mode": "M1 stop-first, same-entry-bar TP deferred",
        "fixed_all_in_fee_usd_per_ounce": 0.40,
        "scenarios_verified": len(complete),
        "trades_matched": sum(x["trades"] for x in complete),
        "fields_per_trade": len(FIELDS),
        "limitations": "M1 cannot establish actual broker tick ordering or fills",
        "scenarios": complete,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--years", nargs="+", type=int, default=list(range(2012, 2020)))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output = verify(args.gold_zip, args.reference_root, args.years)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "years": args.years,
        "scenarios_verified": output["scenarios_verified"],
        "trades_matched": output["trades_matched"],
        "output": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
