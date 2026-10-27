"""Time-aware research splits that prohibit overlapping training and evaluation.

These are structural safeguards, NOT proof of independent OOS performance.
XAUUSD 2020–2026 has already been exposed in previous optimization.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    train_start_utc: str
    train_end_exclusive_utc: str
    eval_start_utc: str
    eval_end_exclusive_utc: str
    embargo_days: int
    evaluation_is_independent: bool = False

    def __post_init__(self) -> None:
        a, b, c, d = [
            pd.Timestamp(x) for x in (
                self.train_start_utc,
                self.train_end_exclusive_utc,
                self.eval_start_utc,
                self.eval_end_exclusive_utc,
            )
        ]
        if any(pd.isna(x) or x.tzinfo is None or str(x.tz) != "UTC" for x in (a, b, c, d)):
            raise ValueError("Fold boundaries must be finite UTC-aware timestamps")
        if not a < b <= c < d:
            raise ValueError("No-lookahead train/eval boundaries violated")
        if type(self.embargo_days) is not int or self.embargo_days < 0:
            raise ValueError("Embargo days must be a nonnegative integer")
        if c - b < pd.Timedelta(days=self.embargo_days):
            raise ValueError("Fold has less than the declared embargo between training and evaluation")


def year_folds(
    *,
    start_year: int,
    last_year: int,
    minimum_train_years: int = 5,
    test_years: int = 1,
    embargo_days: int = 7,
    expanding: bool = True,
) -> list[WalkForwardFold]:
    """Make frozen-year research folds, exclusive UTC boundaries.

    An embargo prevents train/exam overlap and reserves time for overlapping
    positions or features. To avoid overlap at a *trade level*, a separate
    validator MUST additionally purge any open position crossing a boundary.
    """
    if any(type(value) is not int for value in (
        start_year, last_year, minimum_train_years, test_years, embargo_days
    )):
        raise ValueError("Year fold parameters must be integers, not booleans")
    if not 1900 <= start_year < last_year <= 2200:
        raise ValueError("Invalid year range")
    if minimum_train_years < 1 or test_years < 1 or embargo_days < 0:
        raise ValueError("Invalid fold configuration")
    folds = []
    for evaluation_year in range(start_year + minimum_train_years, last_year + 1, test_years):
        train_year = start_year if expanding else evaluation_year - minimum_train_years
        train_start = pd.Timestamp(f"{train_year}-01-01", tz="UTC")
        eval_start = pd.Timestamp(f"{evaluation_year}-01-01", tz="UTC")
        train_end = eval_start - pd.Timedelta(days=embargo_days)
        end_year = min(evaluation_year + test_years, last_year + 1)
        eval_end = pd.Timestamp(f"{end_year}-01-01", tz="UTC")
        if train_end <= train_start:
            continue
        folds.append(
            WalkForwardFold(
                train_start.isoformat(),
                train_end.isoformat(),
                eval_start.isoformat(),
                eval_end.isoformat(),
                embargo_days,
                # Independence is NEVER inferred from a historical date.
                # Proof requires a preregistered, truly unseen dataset.
                evaluation_is_independent=False,
            )
        )
    return folds


def _strict_utc_trade_times(frame: pd.DataFrame, column: str) -> pd.Series:
    """Never silently localize naive or mixed-zone trade timestamps as UTC."""
    if column not in frame:
        raise ValueError(f"Missing {column}")
    if frame.empty:
        return pd.Series(pd.DatetimeIndex([], tz="UTC"), index=frame.index)
    try:
        dates = pd.to_datetime(frame[column], errors="raise", utc=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{column} must contain valid UTC-aware timestamps") from exc
    if not isinstance(dates.dtype, pd.DatetimeTZDtype) or str(dates.dt.tz) != "UTC":
        raise ValueError(f"{column} must contain explicit UTC-aware timestamps")
    if dates.isna().any():
        raise ValueError(f"{column} contains missing timestamps")
    return dates


def require_training_only(frame: pd.DataFrame, fold: WalkForwardFold, *,
                          time_col: str = "closed_at") -> None:
    """Fail when selecting parameters using data outside the train window."""
    dates = _strict_utc_trade_times(frame, time_col)
    a = pd.Timestamp(fold.train_start_utc)
    b = pd.Timestamp(fold.train_end_exclusive_utc)
    if ((dates < a) | (dates >= b)).any():
        raise ValueError("Training selection includes embargo/evaluation/outside records")


def purge_cross_boundary_trades(trades: pd.DataFrame, fold: WalkForwardFold) -> pd.DataFrame:
    """Drop training trades still open at the start of embargo or evaluation."""
    if not {"entry_at", "closed_at"}.issubset(trades):
        raise ValueError("Trade dates required")
    ent = _strict_utc_trade_times(trades, "entry_at")
    close = _strict_utc_trade_times(trades, "closed_at")
    boundary = pd.Timestamp(fold.train_end_exclusive_utc)
    train_start = pd.Timestamp(fold.train_start_utc)
    if (close < ent).any():
        raise ValueError("Trade exits before entry")
    return trades.loc[(ent >= train_start) & (close < boundary)].copy()


def fold_manifest(folds: list[WalkForwardFold]) -> list[dict]:
    return [asdict(fold) for fold in folds]
