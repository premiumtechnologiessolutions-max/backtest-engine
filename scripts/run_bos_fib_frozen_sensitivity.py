"""Reproducible fixed conservative XAUUSD BOS/Fibonacci yearly sensitivity.

Requires a *private*, user-authorized Gold data.zip outside GitHub.
The script runs the ACTUAL installed norisk_quant package. It does not
optimize parameters or claim an independent new holdout.

python scripts/run_bos_fib_frozen_sensitivity.py \
 --gold-zip "/secure/Gold data.zip" --years 2012 2017 2020 2024 \
 --out "/secure/reports/bos_h1_frozen_sensitivity"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from norisk_quant.bos_fib import BosFibSettings, bos_fib_limit_orders
from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.h1_regime import H1RegimeSettings, filter_orders_h1
from norisk_quant.limit_engine import run_limits
from norisk_quant.model import Settings
from norisk_quant.report import report

SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
YEARLY_SETTINGS = BosFibSettings(
    fib_entry=.618, reward_risk=1, ignore_ambiguous_dual_pivots=True
)
H1_SETTINGS = H1RegimeSettings(
    ema_span=50, slope_lag_bars=5, max_regime_age_minutes=120
)
EXECUTION_SETTINGS = Settings(
    ounces=1.0, roundtrip_cost_per_ounce=.40, close_at_end=True
)


def validate_year_selection(years: list[int]) -> None:
    # A float such as 2012.0 or a bool must not silently identify a year.
    if not isinstance(years, (list, tuple)) or not years:
        raise ValueError("Specify at least one selected calendar year")
    if any(type(year) is not int or not 2010 <= year <= 2026 for year in years):
        raise ValueError("Years must be integer calendar years within 2010–2026")
    if len(years) != len(set(years)):
        raise ValueError("Specify distinct selected years without duplicates")


def validate_annual_month_coverage(quotes: pd.DataFrame, year: int) -> None:
    """Fail before backtesting when a nominal annual run omits whole months.

    This is a necessary coverage check, NOT proof of complete minutes,
    broker sessions, genuine ticks, or an independently held-out year.
    """
    index = quotes.index
    if (
        not isinstance(index, pd.DatetimeIndex) or index.empty
        or index.tz is None or str(index.tz) != "UTC"
        or index.hasnans or index.has_duplicates
        or not index.is_monotonic_increasing
    ):
        raise ValueError("Frozen annual M1 requires sorted unique UTC timestamps")
    if (index.year != year).any():
        raise ValueError(f"Annual M1 contains timestamps outside {year}")
    missing = sorted(set(range(1, 13)) - set(index.month.tolist()))
    if missing:
        raise ValueError(
            f"Frozen annual sample {year} omits calendar months: {missing}; "
            "do not report it as a 12-month study"
        )


def execute(gold_zip: Path, years: list[int], destination: Path) -> dict:
    validate_year_selection(years)
    if not gold_zip.is_file() or gold_zip.suffix.lower() != ".zip":
        raise ValueError("Private source must be the original annual JSON ZIP")
    actual_sha = sha256_file(gold_zip)
    if actual_sha != SOURCE_SHA:
        raise ValueError("Original market archive SHA mismatch, fail closed")
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for year in years:
        quotes = load_market(gold_zip, f"{year}-01-01", f"{year}-12-31")
        validate_annual_month_coverage(quotes, year)
        setups = bos_fib_limit_orders(quotes, settings=YEARLY_SETTINGS)
        eligible = filter_orders_h1(quotes, setups, cfg=H1_SETTINGS)
        result = run_limits(quotes, eligible, EXECUTION_SETTINGS)
        subdirectory = destination / str(year)
        summary = report(
            result, EXECUTION_SETTINGS, subdirectory,
            source="original_authorized_private_gold_zip",
            provenance={
                "source_archive_sha256": actual_sha,
                "loaded_m1_bidask_sha256": fingerprint_loaded_m1(quotes),
                "loaded_m1_rows": len(quotes),
            },
            run_parameters={
                "strategy": "bos_fib_m1_frozen_h1_120m_no_dual_pivots",
                "year": year,
                "bos_fib": vars(YEARLY_SETTINGS),
                "h1": vars(H1_SETTINGS),
                "cost_per_oz_all_in": .40,
                "do_not_claim_clean_oos": True,
            },
        )
        trades = len(result.trades)
        total = float(result.trades["net_pnl"].sum())
        if abs(summary["net_pnl"] - total) > 1e-7:
            raise AssertionError("Report P/L differs from executed-trade ledger")
        if abs(summary["total_fees"] - .40 * trades) > 1e-7:
            raise AssertionError("Fee reconciliation mismatch")
        monthly = pd.read_csv(subdirectory / "monthly.csv")
        if (
            len(monthly) != 12
            or summary["months_observed"] != 12
            or summary["months_with_m1_observations"] != 12
        ):
            raise AssertionError("Frozen annual report must contain 12 observed calendar months")
        if abs(float(monthly["net_pnl"].sum()) - total) > 1e-7:
            raise AssertionError("Monthly P/L differs from executed trades")
        weekly = pd.read_csv(subdirectory / "weekly.csv")
        if abs(float(weekly["net_pnl"].sum()) - total) > 1e-7:
            raise AssertionError("Weekly P/L differs from executed trades")
        records.append({
            "year": year,
            "m1_rows": len(quotes),
            "bos_signals": len(setups),
            "h1_signals_after_freshness_and_ambiguity": len(eligible),
            "trades": trades,
            "positive_months": int(summary["positive_months"]),
            "net_usd_1oz": total,
            "all_in_fees_usd": summary["total_fees"],
            "observed_max_drawdown_usd_1oz": summary["max_drawdown_observed_m1"],
            "forced_end_of_data_closures": summary["forced_end_of_data_closures"],
            "same_entry_bar_target_deferred": summary["same_entry_bar_target_deferred"],
            "report_path": f"{year}/summary.json",
        })
    combined = {
        "status": "ACCOUNTING_RECONCILED_NOT_BROKER_CERTIFIED",
        "source_sha256": actual_sha,
        "years_visited_independently": years,
        "trades_total": sum(r["trades"] for r in records),
        "months_profitable_across_separate_calendar_years": sum(r["positive_months"] for r in records),
        "sampled_months": 12 * len(years),
        "sum_of_separate_annual_net_usd_1oz": sum(r["net_usd_1oz"] for r in records),
        "not_continuous_portfolio": True,
        "not_clean_out_of_sample": True,
        "broker_tick_execution_verification": False,
        "annual_results": records,
    }
    (destination / "frozen_sensitivity_summary.json").write_text(
        json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return combined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", default=[2012, 2017, 2020, 2024])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summary = execute(args.gold_zip, args.years, args.out)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
