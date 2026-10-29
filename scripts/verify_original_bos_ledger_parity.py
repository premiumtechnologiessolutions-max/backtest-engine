"""Private raw-archive vs archived-ledger BOS/H1 replay parity release gate.

Runs the actual current No Risk FX limit engine. Never commits/exports quotes
or trade-level records; writes only a sanitized JSON attestation. Historical
comparison is NOT an independently sourced broker execution or fresh OOS.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np
import pandas as pd

from norisk_quant.bos_fib import BosFibSettings, bos_fib_limit_orders
from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.h1_regime import H1RegimeSettings, filter_orders_h1
from norisk_quant.limit_engine import run_limits
from norisk_quant.model import Settings

GOLD_SHA256 = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
REFERENCE_SHA256 = "e90d6fc65ecb1a29f7b7244e14111dea0bbc665879b02c0a3b06865e318563ed"
TOLERANCE = 1e-10

# Independent archived CSV is a prior computation, not a distinct broker feed.
# Preserve all 13 physical execution fields; no summary-only approximation.
FIELDS = {
    "signal_time": "signal_at",
    "entry_time": "entry_at",
    "side": "side",
    "entry": "entry_price",
    "stop": "stop",
    "target": "target",
    "gap_minutes": "gap_minutes",
    "exit_time": "closed_at",
    "exit": "exit_price",
    "exit_reason": "exit_reason",
    "gross": "gross_pnl",
    "fee": "cost",
    "net": "net_pnl",
}
TIMES = frozenset(("signal_time", "entry_time", "exit_time"))
DISCRETE = frozenset(("side", "gap_minutes"))
TEXT = frozenset(("exit_reason",))


def validate_years(years: list[int]) -> None:
    if (type(years) is not list or not years or
            any(type(y) is not int or y not in range(2012, 2020) for y in years)
            or len(set(years)) != len(years)):
        raise ValueError("Archived H1 reference supports distinct years 2012–2019 only")


def compare_trade_fields(actual: pd.DataFrame, archived: pd.DataFrame) -> dict:
    if (not isinstance(actual, pd.DataFrame) or not isinstance(archived, pd.DataFrame)
            or actual.columns.has_duplicates or archived.columns.has_duplicates
            or not set(FIELDS.values()).issubset(actual)
            or not set(FIELDS).issubset(archived)):
        raise ValueError("Incompatible 13-field replay ledger")
    if len(actual) != len(archived):
        raise AssertionError(f"Archived/current trade counts disagree: {len(archived)} vs {len(actual)}")
    largest_difference = 0.0
    for source_name, live_name in FIELDS.items():
        observed = archived[source_name]
        executed = actual[live_name]
        if source_name in TIMES:
            instants = pd.to_datetime(executed, utc=False, errors="raise")
            if (not isinstance(instants.dtype, pd.DatetimeTZDtype)
                    or str(instants.dt.tz) != "UTC" or instants.isna().any()):
                raise ValueError("Executed trade time must be explicitly UTC")
            live = (instants.astype("int64") // 1_000_000_000).to_numpy()
            saved = observed.to_numpy()
            if not np.array_equal(live, pd.to_numeric(saved, errors="raise").to_numpy(dtype=np.int64)):
                raise AssertionError(f"Timestamp drift in {source_name}")
        elif source_name in TEXT:
            if not np.array_equal(executed.astype(str).to_numpy(),
                                  observed.astype(str).to_numpy()):
                raise AssertionError(f"Execution reason drift in {source_name}")
        elif source_name in DISCRETE:
            if not np.array_equal(executed.to_numpy(dtype=np.int64),
                                  pd.to_numeric(observed, errors="raise").to_numpy(dtype=np.int64)):
                raise AssertionError(f"Discrete trade drift in {source_name}")
        else:
            live = executed.to_numpy(dtype=np.float64)
            saved = pd.to_numeric(observed, errors="raise").to_numpy(dtype=np.float64)
            if (not np.isfinite(live).all() or not np.isfinite(saved).all()):
                raise ValueError(f"Nonfinite trade prices or accounting in {source_name}")
            delta = np.abs(live - saved)
            if (delta > TOLERANCE).any():
                raise AssertionError(f"Price/accounting drift in {source_name}, max_delta={float(delta.max())}")
            if len(delta):
                largest_difference = max(largest_difference, float(delta.max()))
    return {"trades": len(actual), "fields_per_trade": len(FIELDS),
            "max_abs_numeric_difference": largest_difference, "mismatched_fields": 0}


def verify(gold_zip: Path, reference_zip: Path, years: list[int]) -> dict:
    validate_years(years)
    for path, expected, label in (
        (gold_zip, GOLD_SHA256, "original Gold source"),
        (reference_zip, REFERENCE_SHA256, "archived execution ledger"),
    ):
        if not isinstance(path, Path) or path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing/unsafe {label}")
        if sha256_file(path) != expected:
            raise ValueError(f"{label} SHA256 mismatch")
    settings = Settings(ounces=1, roundtrip_cost_per_ounce=0.40)
    results = []
    with zipfile.ZipFile(reference_zip) as archive:
        for year in years:
            bars = load_market(gold_zip, f"{year}-01-01", f"{year}-12-31")
            if (len(set(bars.index.month)) != 12 or
                    (bars.index.year != year).any()):
                raise ValueError("Archived replay requires 12 observed calendar months")
            signals = bos_fib_limit_orders(bars, settings=BosFibSettings())
            h1_orders = filter_orders_h1(bars, signals, cfg=H1RegimeSettings())
            alternatives = {
                "h1_only": h1_orders,
                "h1_and_5x": [
                    o for o in h1_orders if abs(o.target - o.price) >= 2.0 - 1e-10
                ],
            }
            scenarios = []
            for label, orders in alternatives.items():
                name = f"results/{year}/{label}/trades.csv"
                try:
                    csv_bytes = archive.read(name)
                except KeyError as exc:
                    raise ValueError(f"Missing exact archived H1 ledger: {name}") from exc
                observed = pd.read_csv(io.BytesIO(csv_bytes))
                executed = run_limits(bars, orders, settings).trades
                verified = compare_trade_fields(executed, observed)
                scenarios.append({"scenario": label, **verified,
                                  "net_usd_per_oz": float(executed["net_pnl"].sum())})
            results.append({"year": year, "loaded_m1_rows": len(bars),
                            "loaded_bidask_sha256": fingerprint_loaded_m1(bars),
                            "scenarios": scenarios})
    if sha256_file(gold_zip) != GOLD_SHA256 or sha256_file(reference_zip) != REFERENCE_SHA256:
        raise ValueError("Private replay source changed before certification")
    return {
        "status": "PASSED_ARCHIVED_13_FIELD_H1_PARITY",
        "source_zip_sha256": GOLD_SHA256,
        "archived_reference_zip_sha256": REFERENCE_SHA256,
        "research_context": "HISTORICAL_EXPOSED_NOT_INDEPENDENT_OOS",
        "broker_tick_fills_verified": False,
        "all_in_fee_usd_per_oz": 0.40,
        "years": years,
        "trades_matched": sum(s["trades"] for y in results for s in y["scenarios"]),
        "fields_per_trade": len(FIELDS),
        "details": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--reference-zip", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", default=[2012])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = verify(args.gold_zip, args.reference_zip, args.years)
    if args.out.is_symlink() or args.out.exists() or not args.out.parent.is_dir():
        raise ValueError("Attestation path must be fresh and owned by the operator")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix=".nrfx-parity-",
        suffix=".json", dir=args.out.parent, delete=False,
    ) as handle:
        staged = Path(handle.name)
        json.dump(result, handle, indent=2)
        handle.write("\n")
    try:
        os.link(staged, args.out)  # exclusive publish; never overwrite
    finally:
        staged.unlink(missing_ok=True)
    print(json.dumps({k: result[k] for k in
        ("status", "years", "trades_matched", "fields_per_trade",
         "broker_tick_fills_verified")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
