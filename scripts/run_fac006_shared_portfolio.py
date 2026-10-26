"""NRF-FAC-006: frozen shared-capacity original-source XAUUSD portfolio.

One actual shared 1-oz slot for three predeclared M15 strategies. Separately
validate three-slot reference against independent canonical run_fast trades
AND every observed M1 equity mark. Exposed design years, NOT clean OOS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal
from norisk_quant.portfolio import (
    PortfolioSettings, run_portfolio, validate_portfolio, write_portfolio_report,
)
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import ORIGINAL
from scripts.batch_h1_range_ema_grid import (
    h1_range_relative, ema_cross_arrays, gated_signals,
)
from scripts.batch_rsi_recross_grid import rsi_recross_arrays

FROZEN = {
    "research_id": "NRF-FAC-006",
    "design_years": [2012, 2013],
    "original_zip_sha256": ORIGINAL,
    "max_entry_delay_minutes": 1,
    "one_ounce_each": True,
    "all_in_fee_per_ounce": .40,
    "priority": "confirmed_at, lexicographic strategy name, original signal order",
    "primary_capacity": {"max_positions": 1, "max_total_ounces": 1.},
    "unconstrained_parity_control": {"max_positions": 3, "max_total_ounces": 3.},
    "signals": {
        "A_RANGE_SLOW": {
            "family": "FAC005B", "fast": 8, "slow": 72, "gate": 1.,
            "stop": 6.5, "target": 1.,
            "selection": "post-hoc selected on exposed 2012/13 historical data",
        },
        "B_RANGE_FAST": {
            "family": "FAC005B", "fast": 16, "slow": 26, "gate": .8,
            "stop": 8., "target": 10.,
            "selection": "post-hoc selected on exposed 2012/13 historical data",
        },
        "C_RSI_BASE": {
            "family": "FAC004", "period": 14, "threshold": 30,
            "stop": 4., "target": 4.,
            "selection": "fixed neutral research comparator, not validated",
        },
    },
    "warning": "Portfolio research is in-sample, with post-hoc candidate selection, not OOS or live advice",
}


def build_signals(m1: pd.DataFrame) -> dict[str, list[Signal]]:
    m15 = aggregate_bars(m1, "M15")
    h1 = aggregate_bars(m1, "H1")
    h1_ratio = h1_range_relative(h1)
    h1_stamps = np.asarray(h1["close_at"].array.asi8 // 1_000_000_000, dtype=np.int64)
    result: dict[str, list[Signal]] = {}
    for name, spec in FROZEN["signals"].items():
        if spec["family"] == "FAC005B":
            t, side = ema_cross_arrays(m15, spec["fast"], spec["slow"])
            t, side = gated_signals(t, side, h1_stamps, h1_ratio, spec["gate"])
        else:
            t, side = rsi_recross_arrays(m15, spec["period"], spec["threshold"])
        result[name] = [
            Signal(
                confirmed_at=pd.Timestamp(int(at), unit="s", tz="UTC"),
                side=int(direction), stop_distance=float(spec["stop"]),
                target_distance=float(spec["target"]), strategy=name,
            )
            for at, direction in zip(t, side)
        ]
    return result


def _settings(slots: int) -> PortfolioSettings:
    return PortfolioSettings(
        ounces_by_strategy={name: 1. for name in FROZEN["signals"]},
        max_open_positions=slots, max_total_ounces=float(slots),
        max_entry_delay_minutes=1, close_at_end=True,
        all_in_cost_per_ounce=.40,
    )


def _monthly_net(trades: pd.DataFrame) -> np.ndarray:
    return np.bincount(
        pd.to_datetime(trades.closed_at, utc=True).dt.month,
        weights=trades.net_pnl.to_numpy(dtype=float),
        minlength=13,
    )[1:]


def run_frozen(m1: pd.DataFrame, *, year: int, out: Path) -> dict:
    if type(year) is not int or year not in (2012, 2013):
        raise ValueError("Only frozen 2012 and 2013 exposed design years")
    out = Path(out)
    if (out / "research_summary.json").exists():
        raise FileExistsError("Refuse to overwrite completed portfolio research")
    out.mkdir(parents=True, exist_ok=True)
    frozen = out / "frozen_portfolio.json"
    if frozen.exists() and json.loads(frozen.read_text()) != FROZEN:
        raise ValueError("Conflicting frozen portfolio")
    frozen.write_text(json.dumps(FROZEN, indent=2), encoding="utf-8")
    components = build_signals(m1)
    all_signals = [sig for name in FROZEN["signals"] for sig in components[name]]
    if not all_signals:
        raise AssertionError("Frozen portfolio has no signals on original source")

    control_settings = _settings(3)
    control = run_portfolio(m1, all_signals, control_settings)
    control_audit = validate_portfolio(control, control_settings)
    refs = {
        name: run_fast(
            m1, sig, Settings(
                ounces=1., roundtrip_cost_per_ounce=.40,
                max_entry_delay_minutes=1, close_at_end=True,
            ),
        )
        for name, sig in components.items()
    }
    ref_trades = sum(len(x.trades) for x in refs.values())
    ref_fees = sum(float(x.trades.cost.sum()) for x in refs.values())
    ref_monthly = sum((_monthly_net(x.trades) for x in refs.values()),
                      np.zeros(12, dtype=float))
    ref_equity = sum(
        (x.equity.equity.to_numpy(dtype=float) for x in refs.values()),
        np.zeros(len(m1), dtype=float),
    )
    ctrl_monthly = _monthly_net(control.trades)
    max_month_diff = float(np.max(np.abs(ref_monthly - ctrl_monthly)))
    max_equity_diff = float(np.max(np.abs(
        ref_equity - control.equity.equity.to_numpy(dtype=float)
    )))
    control_parity = {
        "canonical_reference_trades": ref_trades,
        "shared_three_slot_trades": len(control.trades),
        "canonical_reference_fees": ref_fees,
        "shared_three_slot_fees": float(control.trades.cost.sum()),
        "max_monthly_net_delta": max_month_diff,
        "max_observed_m1_equity_delta": max_equity_diff,
        "shared_three_slot_capacity_rejected": control.capacity_rejected,
    }
    if (ref_trades != len(control.trades)
        or abs(ref_fees - float(control.trades.cost.sum())) > 1e-7
        or max_month_diff > 1e-7 or max_equity_diff > 1e-7
        or control.capacity_rejected != 0):
        raise AssertionError(
            f"Three-slot portfolio diverged from independent run_fast: {control_parity}"
        )
    control_summary = write_portfolio_report(
        control, control_settings, out / "control_three_slots"
    )

    primary_settings = _settings(1)
    primary = run_portfolio(m1, all_signals, primary_settings)
    primary_audit = validate_portfolio(primary, primary_settings)
    primary_summary = write_portfolio_report(
        primary, primary_settings, out / "primary_one_slot"
    )
    primary_monthly = _monthly_net(primary.trades)
    if (primary.equity.open_positions.max() > 1
        or primary.equity.gross_open_ounces.max() > 1. + 1e-12):
        raise AssertionError("One-slot shared capacity was breached")
    summary = {
        "status": "COMPLETED_HISTORICALLY_EXPOSED_IN_SAMPLE_PORTFOLIO_NOT_OOS",
        "year": year,
        "original_zip_sha256": ORIGINAL,
        "loaded_m1_sha256": fingerprint_loaded_m1(m1),
        "observed_m1_rows": len(m1),
        "confirmed_signals_by_strategy": {
            name: len(sig) for name, sig in components.items()
        },
        "unconstrained_canonical_parity": control_parity,
        "control_accounting": control_audit,
        "primary_accounting": primary_audit,
        "control_annual_net": float(control.trades.net_pnl.sum()),
        "control_positive_months": int((ctrl_monthly > 0).sum()),
        "primary_annual_net": float(primary.trades.net_pnl.sum()),
        "primary_positive_months": int((primary_monthly > 0).sum()),
        "primary_worst_month": float(primary_monthly.min()),
        "primary_floating_max_dd": primary_summary["max_observed_m1_close_drawdown"],
        "primary_trades": len(primary.trades),
        "primary_capacity_rejected": primary.capacity_rejected,
        "primary_duplicate_strategy_rejected": primary.duplicate_strategy_rejected,
        "control_report_summary": {
            "max_observed_m1_close_drawdown": control_summary["max_observed_m1_close_drawdown"],
            "max_open_positions": control_summary["max_observed_open_positions"],
        },
        "primary_monthly": [float(v) for v in primary_monthly],
        "control_monthly": [float(v) for v in ctrl_monthly],
        "warning": "Two components historically selected from same design years. No independent OOS, no live advice.",
    }
    (out / "research_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if sha256_file(args.gold_zip) != ORIGINAL:
        raise ValueError("Refuse wrong private gold archive")
    m1 = load_market(args.gold_zip, f"{args.year}-01-01", f"{args.year}-12-31")
    print(json.dumps(run_frozen(m1, year=args.year, out=args.out), indent=2))


if __name__ == "__main__":
    main()
