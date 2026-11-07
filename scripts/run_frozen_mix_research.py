"""Frozen multi-family XAUUSD research round; executed offline on private ZIP.

No strategy fitting, no historical OOS claims, no market data uploaded.
All families share ONE real Market+Limit portfolio (two open positions).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from norisk_quant.data import sha256_file, fingerprint_loaded_m1, load_market
from norisk_quant.fvg import fvg_midpoint_limit_orders
from norisk_quant.liquidity_sweep import SweepSettings, liquidity_sweep_signals
from norisk_quant.portfolio import PortfolioSettings, write_portfolio_report
from norisk_quant.portfolio_unified import run_unified_portfolio
from norisk_quant.strategies_native import donchian_breakout_signals
from norisk_quant.strategy import ema_cross_signals

SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
SPEC = {
    "hypothesis": "sweep_reclaim_plus_trend_breakout_plus_gap_fill",
    "design_years": [2012, 2013, 2014, 2015, 2016],
    "candidates": {
        "donchian": {"timeframe": "H1", "lookback": 20, "stop_distance": 15.0,
                     "target_distance": 30.0},
        "ema": {"timeframe": "M15", "fast": 9, "slow": 21,
                "stop_atr": 1.5, "rr": 2.0},
        "sweep_m15": {"timeframe": "M15", "lookback_bars": 12,
                      "penetration_usd": 0.25, "stop_buffer_usd": 0.1,
                      "reward_risk": 1.5, "min_stop_usd": 0.5, "max_stop_usd": 50.0},
        "sweep_h1": {"timeframe": "H1", "lookback_bars": 12,
                     "penetration_usd": 0.25, "stop_buffer_usd": 0.1,
                     "reward_risk": 1.5, "min_stop_usd": 0.5, "max_stop_usd": 50.0},
        "fvg": {"timeframe": "H1", "min_gap_usd": 0.5,
                "stop_buffer_usd": 0.1, "reward_to_risk": 2.0, "expiry_hours": 20.0},
    },
    "shared_capacity": {"max_open_positions": 2, "max_total_ounces": 2.0,
                        "ounces_each": 1.0, "all_in_cost_per_ounce": 0.4},
    "selection_policy": "Design results only; no threshold fitting or independent OOS claim",
}
SPEC_SHA256 = hashlib.sha256(json.dumps(
    SPEC, sort_keys=True, separators=(",", ":")
).encode()).hexdigest()
FIXED_NAMES = (
    "donchian_close_H1_20_fixedSLTP", "ema_cross_M15_9_21",
    "sweep_reclaim_M15_12", "sweep_reclaim_H1_12",
    "fvg3_ce_H1_bullish", "fvg3_ce_H1_bearish",
)


def execute(gold_zip: Path, out: Path, year: int) -> dict:
    if type(year) is not int or year not in SPEC["design_years"]:
        raise ValueError("Only predeclared design years 2012–2016")
    if sha256_file(gold_zip) != SOURCE_SHA:
        raise ValueError("Private original gold source SHA mismatch")
    if (out / "summary.json").exists():
        raise FileExistsError("Refusing to overwrite an earlier research report")
    data = load_market(gold_zip, f"{year}-01-01", f"{year}-12-31")
    settings = SPEC["candidates"]
    market = [
        *donchian_breakout_signals(data, **settings["donchian"]),
        *ema_cross_signals(data, **settings["ema"]),
        *liquidity_sweep_signals(data, settings=SweepSettings(**settings["sweep_m15"])),
        *liquidity_sweep_signals(data, settings=SweepSettings(**settings["sweep_h1"])),
    ]
    limit_orders = fvg_midpoint_limit_orders(data, **settings["fvg"])
    encountered = {s.strategy for s in market} | {o.strategy for o in limit_orders}
    if not encountered.issubset(FIXED_NAMES):
        raise ValueError("A strategy label drifted from frozen research contract")
    portfolio = PortfolioSettings(
        ounces_by_strategy={name: 1.0 for name in FIXED_NAMES},
        max_open_positions=2, max_total_ounces=2.0, all_in_cost_per_ounce=0.40,
    )
    result = run_unified_portfolio(data, market, limit_orders, portfolio)
    summary = write_portfolio_report(result, portfolio, out)
    record = {
        "status": "COMPLETED_DESIGN_ONLY_NOT_OOS", "year": year,
        "source_sha256": SOURCE_SHA, "candidate_spec_sha256": SPEC_SHA256,
        "loaded_m1_sha256": fingerprint_loaded_m1(data),
        "m1_rows": int(len(data)), "market_signals": len(market),
        "limit_orders": len(limit_orders), "families": list(FIXED_NAMES),
        "trades": summary["trades"],
        "positive_months": summary["portfolio_profitable_observed_months"],
        "nonpositive_months": summary["portfolio_nonprofitable_observed_months"],
        "net_pnl": summary["net_pnl_closed"],
        "max_m1_drawdown": summary["max_observed_m1_close_drawdown"],
        "caveat": "Annual reset and synthetic M1 fills; exposed design period, NOT independent OOS",
    }
    (out / "frozen_spec.json").write_text(json.dumps(SPEC, indent=2), encoding="utf-8")
    (out / "research_round.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.gold_zip, args.out, args.year), indent=2))


if __name__ == "__main__":
    main()
