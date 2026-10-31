"""Private XAUUSD 2024 M1 fixture: shared Limit replay versus two single runs.

The source ZIP is local-only and MUST NOT be committed to GitHub. These
orders are synthetic deterministic fixtures, not trading recommendations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from norisk_quant.limit_engine import LimitOrder, run_limits
from norisk_quant.model import Settings
from norisk_quant.portfolio import PortfolioSettings, validate_portfolio
from norisk_quant.portfolio_limits import run_limit_portfolio

GOLD_SHA256 = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
WINDOWS = (0, 12000, 25000, 40000, 70000, 120000, 180000, 250000, 300000, 350000)


def verify(source: Path) -> dict:
    h = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != GOLD_SHA256:
        raise ValueError("Original private Gold data.zip SHA-256 mismatch")
    with zipfile.ZipFile(source) as archive:
        raw = pd.DataFrame(json.loads(archive.read("2024.json")))
    raw.index = pd.to_datetime(raw["ts"], unit="s", utc=True)
    market = raw[["o", "h", "l", "c"]]
    if market.index.has_duplicates or not market.index.is_monotonic_increasing:
        raise ValueError("Unordered original M1 observations")
    if (market.index.asi8 % 60_000_000_000 != 0).any():
        raise ValueError("Source M1 not aligned to minute opens")
    rows = []
    for number, offset in enumerate(WINDOWS, start=1):
        bars = market.iloc[offset:offset + 300]
        if len(bars) != 300:
            raise ValueError("Unexpected 2024 M1 sample length")
        at = bars.index[10] + pd.Timedelta(minutes=1)
        entry = float(bars["c"].iloc[10])
        orders = [
            LimitOrder(at, at + pd.Timedelta(minutes=5), 1,
                       entry, entry - 1.5, entry + 2.0, "a"),
            LimitOrder(at, at + pd.Timedelta(minutes=5), -1,
                       entry, entry + 1.5, entry - 2.0, "b"),
        ]
        cfg = PortfolioSettings({"a": 1.0, "b": 1.0},
                                max_open_positions=2, max_total_ounces=2.0)
        shared = run_limit_portfolio(bars, orders, cfg)
        independent = [run_limits(bars, [order], Settings()) for order in orders]
        for name, single in zip(("a", "b"), independent):
            actual = shared.trades.loc[shared.trades["strategy"] == name].reset_index(drop=True)
            pd.testing.assert_frame_equal(actual, single.trades.reset_index(drop=True),
                                          check_dtype=False, rtol=0, atol=1e-7)
        expected = independent[0].equity["equity"] + independent[1].equity["equity"]
        max_delta = float(np.max(np.abs(expected - shared.equity["equity"])))
        if max_delta > 1e-7:
            raise AssertionError(f"Shared equity differs by {max_delta}")
        validate_portfolio(shared, cfg)
        rows.append({
            "window": number, "start_utc": bars.index[0].isoformat(),
            "end_utc": bars.index[-1].isoformat(),
            "matched_trades": int(len(shared.trades)),
            "fee_usd": float(shared.trades["cost"].sum()),
            "max_equity_delta_usd": max_delta,
        })
    return {
        "status": "PASSED", "original_zip_sha256": GOLD_SHA256,
        "observed_2024_m1": int(len(market)),
        "fixture_windows": len(rows), "m1_samples": 300 * len(rows),
        "matched_trades": sum(row["matched_trades"] for row in rows),
        "max_equity_delta_usd": max(row["max_equity_delta_usd"] for row in rows),
        "all_in_cost_usd_per_ounce_roundtrip": 0.40,
        "git_revision_env": os.environ.get("GITHUB_SHA"),
        "scope_warning": (
            "Exact package Limit/Portfolio M1 replay consistency on predeclared "
            "synthetic fixture orders and real 2024 BID candles only; not full "
            "GitHub CI, BOS historical parity, broker tick fills or profitable strategy evidence."
        ),
        "windows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.gold_zip)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "windows"}, indent=2))


if __name__ == "__main__":
    main()
