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
import hashlib
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
        }),
        ("archive", reference, {
            "signal": "signal_time", "entry_time": "entry_time",
            "exit_time": "exit_time", "entry": "entry",
            "exit": "exit", "stop": "stop", "target": "target",
            "fee": "fee", "gross": "gross", "net": "net",
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


def verify(gold_zip: Path, reference_root: Path, years: list[int]) -> dict:
    validate_replay_years(years)
    sha = file_sha256(gold_zip)
    if sha != EXPECTED_MARKET_SHA256:
        raise ValueError("Dataset SHA-256 differs from archived reference gold source")
    yearly = pd.read_csv(reference_root / "yearly.csv")
    complete = []
    for year in years:
        # Read annual JSON only and don't allow unseen feed replacement.
        m1 = load_market(gold_zip, f"{year}-01-01", f"{year}-12-31")
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
            baseline = pd.read_csv(
                reference_root / "results" / str(year) / name / "trades.csv"
            )
            check = exact_ledger_check(result.trades, baseline)
            summary_row = yearly.loc[
                (yearly["year"] == year) & (yearly["variant"] == name)
            ]
            if len(summary_row) != 1:
                raise AssertionError("Missing or duplicate year/variant reference")
            expected_count = int(summary_row.iloc[0]["trades"])
            expected_orders = int(summary_row.iloc[0]["orders"])
            if len(orders) != expected_orders or check["trades"] != expected_count:
                raise AssertionError("Signal count or trade count does not reconcile")
            total = float(result.trades["net_pnl"].sum())
            if not np.isclose(total, float(summary_row.iloc[0]["net_usd_oz"]), rtol=0, atol=1e-6):
                raise AssertionError("Annual P/L fails standalone reference reconciliation")
            complete.append({
                "year": year,
                "variant": name,
                "M1_rows": len(m1),
                "signals": len(orders),
                "net_usd_1oz": total,
                "deferred_same_entry_bar_TP": result.uncertain_entry_tp_deferred,
                **check,
                "status": "PASSED",
            })
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
