"""New engine acceptance gates on private annual JSON; no strategy selection.

Checks actual reference/fast Donchian parity and independent Market + Limit
fixture ledgers against unified shared execution. The fixtures are execution
tests on real quotes, not profitable strategy candidates. Raw quotes remain
outside this repository. Reports must also stay outside the source tree.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import pandas as pd

from norisk_quant.accounting import validate_execution
from norisk_quant.data import fingerprint_loaded_m1, quality, read_source, sha256_file
from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.limit_engine import LimitOrder, run_limits
from norisk_quant.model import Settings, Signal
from norisk_quant.portfolio import PortfolioSettings, validate_portfolio
from norisk_quant.portfolio_unified import run_unified_portfolio, write_unified_portfolio_report
from norisk_quant.strategies_native import donchian_breakout_signals


def compare(left: pd.DataFrame, right: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(left, right, check_dtype=False, check_freq=False,
                                  check_exact=False, rtol=0, atol=1e-8)


def sorted_trades(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["strategy", "entry_at", "closed_at"]).reset_index(drop=True)


def fixtures(data: pd.DataFrame) -> tuple[list[Signal], list[LimitOrder]]:
    """Sparse fixed fixtures formed strictly from the just-completed M1 close."""
    signals, orders = [], []
    for number, i in enumerate(range(240, len(data) - 2, 1000)):
        confirmed = data.index[i] + pd.Timedelta(minutes=1)
        close = float(data.c.iloc[i])
        side = 1 if number % 2 == 0 else -1
        signals.append(Signal(confirmed, side, 1.0, 1.5, "fixture_market"))
        price = close + side * 0.25  # opposing limit, below/above known close
        orders.append(LimitOrder(confirmed, confirmed + pd.Timedelta(minutes=60),
                                 -side, price, price + side * 1.0,
                                 price - side * 1.5, "fixture_limit"))
    return signals, orders


def reconcile_source_marks(result, data: pd.DataFrame) -> None:
    """Rebuild open quantity, count and every floating mark from original closes."""
    floating = np.zeros(len(data), dtype=float)
    ounces = np.zeros(len(data), dtype=float)
    positions = np.zeros(len(data), dtype=int)
    for trade in result.trades.itertuples():
        left = data.index.get_loc(trade.entry_at)
        right = data.index.get_loc(trade.closed_at)
        floating[left:right] += (trade.side * (data.c.iloc[left:right].to_numpy()
                                               - trade.entry_price) * trade.ounces
                                - 0.40 * trade.ounces)
        ounces[left:right] += trade.ounces
        positions[left:right] += 1
    np.testing.assert_allclose(floating, result.equity.floating_pnl, rtol=0, atol=1e-8)
    np.testing.assert_allclose(ounces, result.equity.gross_open_ounces, rtol=0, atol=1e-8)
    np.testing.assert_array_equal(positions, result.equity.open_positions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    destination = args.out.resolve()
    if destination == repo or repo in destination.parents:
        parser.error("Keep private quote-derived ledgers outside the repository")
    destination.mkdir(parents=True, exist_ok=True)
    begin = time.perf_counter()
    data = read_source(args.json)
    if data.index.year.nunique() != 1:
        raise ValueError("Expected one annual JSON")
    quality_report = quality(data)
    # Verify real Parquet support and preservation, independently of pytest mocks.
    parquet = destination / "private_roundtrip.parquet"
    data.to_parquet(parquet)
    compare(data, pd.read_parquet(parquet))
    provenance = {"annual_json_sha256": sha256_file(args.json),
                  "loaded_m1_bidask_sha256": fingerprint_loaded_m1(data),
                  "original_zip_identity": "not_available_not_verified"}
    canonical = Settings(ounces=1, roundtrip_cost_per_ounce=0.40)
    signals = donchian_breakout_signals(data)
    reference, fast = run(data, signals, canonical), run_fast(data, signals, canonical)
    compare(reference.trades, fast.trades)
    compare(reference.equity, fast.equity)
    assert (reference.pending_at_end, reference.expired_signals) == (
        fast.pending_at_end, fast.expired_signals)
    reference_audit = validate_execution(reference, canonical)
    fast_audit = validate_execution(fast, canonical)
    del reference, fast

    market_signals, orders = fixtures(data)
    settings_market = Settings(ounces=0.5)
    settings_limit = Settings(ounces=1.25)
    market = run(data, market_signals, settings_market)
    limit = run_limits(data, orders, settings_limit)
    validate_execution(market, settings_market)
    validate_execution(limit, settings_limit)
    shared = PortfolioSettings({"fixture_market": 0.5, "fixture_limit": 1.25},
                               max_open_positions=2, max_total_ounces=1.75)
    unified = run_unified_portfolio(data, market_signals, orders, shared)
    baseline = pd.concat([market.trades, limit.trades], ignore_index=True)
    compare(sorted_trades(baseline), sorted_trades(unified.trades[baseline.columns]))
    compare(market.equity + limit.equity,
            unified.equity[["realized_pnl", "floating_pnl", "equity"]])
    # Independent per-minute floating reconciliation from entry/exit ledger and
    # observed close prices. This covers each position, not just final totals.
    reconcile_source_marks(unified, data)
    audit = validate_portfolio(unified, shared)
    summary = write_unified_portfolio_report(unified, shared, destination / "unified")
    for filename in ("monthly.csv", "weekly.csv"):
        periods = pd.read_csv(destination / "unified" / filename)
        if periods.equity_change.isna().any():
            raise ValueError(f"Whole missing period prevents allocated P/L gate: {filename}")
        np.testing.assert_allclose(periods.net_pnl.sum(), unified.trades.net_pnl.sum(),
                                   rtol=0, atol=1e-8)
        np.testing.assert_allclose(periods.equity_change.sum(), unified.equity.equity.iloc[-1],
                                   rtol=0, atol=1e-8)

    constrained_settings = PortfolioSettings(shared.ounces_by_strategy,
                                             max_open_positions=1, max_total_ounces=1.25)
    constrained = run_unified_portfolio(data, market_signals, orders, constrained_settings)
    constrained_audit = validate_portfolio(constrained, constrained_settings)
    reconcile_source_marks(constrained, data)
    assert constrained.capacity_rejected > 0
    write_unified_portfolio_report(constrained, constrained_settings, destination / "constrained")
    manifest = {
        "status": "PASSED", "purpose": "EXECUTION_PARITY_NOT_PROFIT_RESEARCH",
        "code_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo,
                                                  text=True).strip(),
        "code_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"],
                                                         cwd=repo, text=True).strip()),
        "source": provenance, "quality": quality_report,
        "reference_fast": {"signals": len(signals), "reference_audit": reference_audit,
                           "fast_audit": fast_audit, "all_trade_fields": "PASSED",
                           "all_observed_m1_equity": "PASSED", "signal_counters": "PASSED"},
        "unified": {"settings": asdict(shared), "fixtures_market": len(market_signals),
                    "fixtures_limit": len(orders), "audit": audit,
                    "independent_trade_and_equity_parity": "PASSED",
                    "independent_per_position_floating_reconciliation": "PASSED",
                    "weekly_monthly_reconciliation": "PASSED", "summary": summary},
        "constrained": {"audit": constrained_audit,
                        "independent_per_position_floating_reconciliation": "PASSED",
                        "capacity_rejected": constrained.capacity_rejected},
        "elapsed_seconds": round(time.perf_counter() - begin, 3),
        "limits": "Synthetic common BID OHLC reference; no broker tick/margin validation or profit claim.",
    }
    (destination / "verification.json").write_text(json.dumps(manifest, indent=2, default=str),
                                                 encoding="utf-8")
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
