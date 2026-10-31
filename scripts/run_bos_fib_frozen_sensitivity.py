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
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd

# Works both as `python -m scripts.run_bos_fib_frozen_sensitivity` and
# as `python scripts/run_bos_fib_frozen_sensitivity.py` from the repo root.
if __package__:
    from .frozen_evidence_manifest import write_evidence_manifest
    from .frozen_summary_integrity import verify_frozen_summary_claims
    from .frozen_parameter_contract import verify_frozen_parameter_contract
else:
    from frozen_evidence_manifest import write_evidence_manifest
    from frozen_summary_integrity import verify_frozen_summary_claims
    from frozen_parameter_contract import verify_frozen_parameter_contract
from norisk_quant.bos_fib import BosFibSettings, bos_fib_limit_orders
from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.evidence_reconciliation import verify_exit_periods
from norisk_quant.h1_regime import H1RegimeSettings, filter_orders_h1
from norisk_quant.limit_engine import run_limits
from norisk_quant.model import Settings
from norisk_quant.persisted_trade_integrity import verify_persisted_trade_ledger
from norisk_quant.report import report
from norisk_quant.source_exit_integrity import OPEN_REASONS, verify_source_open_exit_prices
from norisk_quant.source_bar_exit_integrity import AUDITED_REASONS, verify_source_bar_exit_prices
from norisk_quant.source_gap_integrity import verify_source_gap_minutes

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



def validate_output_destination(destination: Path) -> None:
    """Do not overwrite earlier frozen replay evidence or follow output symlinks."""
    # A non-symlink final directory can still escape through a symlinked
    # parent. Reject the entire existing ancestor chain before any report is
    # created; this is a preflight guard, not a defense against concurrent
    # filesystem replacement by an adversary.
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise FileExistsError("Frozen report destination or parent must not be a symlink")
    if destination.exists():
        if not destination.is_dir():
            raise FileExistsError("Frozen report destination exists and is not a directory")
        if any(destination.iterdir()):
            raise FileExistsError(
                "Frozen report destination is nonempty; choose a fresh output path"
            )



def verify_exit_audit_coverage(
    trades: pd.DataFrame, open_verified: int, by_reason: dict[str, int]
) -> None:
    """Require every executed exit to be independently source-bar audited.

    The lower-level source checkers intentionally skip unfamiliar labels.
    The frozen annual runner must NOT silently certify an unverified new
    execution path, even when monthly and weekly P/L totals reconcile.
    """
    if (not isinstance(trades, pd.DataFrame) or trades.columns.has_duplicates
            or "exit_reason" not in trades.columns):
        raise ValueError("Frozen exit coverage requires a unique exit_reason column")
    if type(by_reason) is not dict or set(by_reason) != AUDITED_REASONS:
        raise AssertionError("Frozen source-bar audit reason set changed")
    if any(type(count) is not int or count < 0 for count in by_reason.values()):
        raise AssertionError("Frozen source-bar audit counts must be nonnegative integers")
    actual = trades["exit_reason"].value_counts(dropna=False).to_dict()
    if any(type(reason) is not str or reason not in AUDITED_REASONS for reason in actual):
        raise AssertionError("Frozen replay contains an unaudited exit reason")
    if any(by_reason[reason] != actual.get(reason, 0) for reason in AUDITED_REASONS):
        raise AssertionError("Frozen source-bar audit does not cover every executed exit")
    expected_open = sum(actual.get(reason, 0) for reason in OPEN_REASONS)
    if type(open_verified) is not int or open_verified != expected_open:
        raise AssertionError("Frozen source-open audit count disagrees with executed exits")


def execute(gold_zip: Path, years: list[int], destination: Path) -> dict:
    """Publish an annual replay only after *every* selected year passes.

    A later-year failure or final source-SHA mismatch must not leave earlier
    annual reports at the requested destination, where they might be mistaken
    for a completed frozen study. Temporary evidence remains a sibling of
    the destination and is removed on every failure.
    """
    validate_year_selection(years)
    validate_output_destination(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    validate_output_destination(destination)
    staging = Path(tempfile.mkdtemp(
        prefix=f".{destination.name}.staging-", dir=destination.parent
    ))
    try:
        combined = _execute_unpublished(gold_zip, years, staging)
        # Recheck before publishing: a concurrent writer may have populated
        # the destination while the multi-year replay was running.
        validate_output_destination(destination)
        os.replace(staging, destination)
        return combined
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _execute_unpublished(gold_zip: Path, years: list[int], destination: Path) -> dict:
    validate_year_selection(years)
    validate_output_destination(destination)
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
        source_open_exits_verified = verify_source_open_exit_prices(quotes, result.trades)
        source_bar_exits_verified = verify_source_bar_exit_prices(quotes, result.trades)
        verify_exit_audit_coverage(result.trades, source_open_exits_verified,
                                   source_bar_exits_verified)
        source_gap_minutes_verified = verify_source_gap_minutes(quotes, result.trades)
        if source_gap_minutes_verified != len(result.trades):
            raise AssertionError("Frozen source gap audit did not cover all executed trades")
        loaded_fingerprint = fingerprint_loaded_m1(quotes)
        subdirectory = destination / str(year)
        summary = report(
            result, EXECUTION_SETTINGS, subdirectory,
            source="original_authorized_private_gold_zip",
            provenance={
                "source_archive_sha256": actual_sha,
                "loaded_m1_bidask_sha256": loaded_fingerprint,
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
        # Aggregate sums alone cannot detect a fabricated redistribution of P/L
        # between months or weeks. Recompute each UTC exit bucket from the
        # persisted trade ledger before certifying the frozen annual report.
        exported_trades = pd.read_csv(subdirectory / "trades.csv")
        # Compare persisted trades with the ACTUAL in-memory executor ledger.
        # Matching period totals cannot detect altered prices, timestamps,
        # direction, or trade order when the P/L sum remains unchanged.
        verify_persisted_trade_ledger(result.trades, exported_trades)
        verify_exit_periods(
            monthly.to_dict(orient="records"),
            weekly.to_dict(orient="records"),
            exported_trades.to_dict(orient="records"),
            first_utc_date=f"{year}-01-01",
            last_utc_date=f"{year}-12-31",
        )
        # Verify the persisted headline summary independently against the
        # executed trades, month buckets, original-source fingerprints and
        # frozen strategy/disclaimer. A valid file hash alone cannot certify
        # that the headline claims are true.
        persisted_summary = json.loads(
            (subdirectory / "summary.json").read_text(encoding="utf-8")
        )
        if persisted_summary != summary:
            raise ValueError("Frozen persisted annual summary differs from report return")
        verify_frozen_summary_claims(
            persisted_summary, monthly, result.trades,
            year=year, source_sha=actual_sha,
            bidask_sha=loaded_fingerprint, m1_rows=len(quotes),
        )
        # Independently pin every recorded BOS/H1 setting, not merely the
        # strategy label. A changed dataclass default must not be certified
        # as the 2026-10-25 preregistered frozen experiment.
        verify_frozen_parameter_contract(
            persisted_summary["run_parameters"], year=year,
        )
        records.append({
            "year": year,
            "m1_rows": len(quotes),
            "bos_signals": len(setups),
            "h1_signals_after_freshness_and_ambiguity": len(eligible),
            "trades": trades,
            "source_open_stop_exits_verified": source_open_exits_verified,
            "source_bar_exits_verified_by_reason": source_bar_exits_verified,
            "source_gap_minutes_verified": source_gap_minutes_verified,
            "positive_months": int(summary["positive_months"]),
            "net_usd_1oz": total,
            "all_in_fees_usd": summary["total_fees"],
            "observed_max_drawdown_usd_1oz": summary["max_drawdown_observed_m1"],
            "forced_end_of_data_closures": summary["forced_end_of_data_closures"],
            "same_entry_bar_target_deferred": summary["same_entry_bar_target_deferred"],
            "report_path": f"{year}/summary.json",
        })
    # A source archive can be replaced after the initial SHA check while the
    # annual loader is still reading it. Do not certify a replay under the
    # original source identity if the on-disk ZIP changed during the run.
    # This detects persistent mutation, not adversarial swap-and-restore races.
    if sha256_file(gold_zip) != actual_sha:
        raise ValueError("Original market archive changed during frozen replay")
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
        "evidence_manifest": "evidence_manifest.json",
    }
    (destination / "frozen_sensitivity_summary.json").write_text(
        json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    # The report tree is still unpublished. Pin every exported byte to a
    # deterministic SHA256 inventory before the atomic destination rename.
    write_evidence_manifest(destination, years, actual_sha)
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
