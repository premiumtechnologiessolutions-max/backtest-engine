"""Time-aware research splits that prohibit overlapping training and evaluation.

These are structural safeguards, NOT proof of independent OOS performance.
XAUUSD 2020–2026 has already been exposed in previous optimization.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta

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
        if any(x.tzinfo is None for x in (a, b, c, d)):
            raise ValueError("Fold boundaries must include UTC timezone")
        if not a < b <= c < d:
            raise ValueError("No-lookahead train/eval boundaries violated")
        if self.embargo_days < 0:
            raise ValueError("Negative embargo")


def year_folds(
    *,
    start_year: int,
    last_year: int,
    minimum_train_years: int = 5,
    test_years: int = 1,
    embargo_days: int = 7,
    expanding: bool = True,
    exposed_from_year: int = 2020,
) -> list[WalkForwardFold]:
    """Make frozen-year research folds, exclusive UTC boundaries.

    An embargo prevents train/exam overlap and reserves time for overlapping
    positions or features. To avoid overlap at a *trade level*, a separate
    validator MUST additionally purge any open position crossing a boundary.
    """
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
                evaluation_is_independent=(evaluation_year < exposed_from_year),
            )
        )
    return folds


def require_training_only(frame: pd.DataFrame, fold: WalkForwardFold, *,
                          time_col: str = "closed_at") -> None:
    """Fail when selecting parameters using data outside the train window."""
    if time_col not in frame:
        raise ValueError(f"Missing {time_col}")
    dates = pd.to_datetime(frame[time_col], utc=True, errors="raise")
    if dates.isna().any():
        raise ValueError("Missing dates in training records")
    a = pd.Timestamp(fold.train_start_utc)
    b = pd.Timestamp(fold.train_end_exclusive_utc)
    if ((dates < a) | (dates >= b)).any():
        raise ValueError("Training selection includes embargo/evaluation/outside records")


def purge_cross_boundary_trades(trades: pd.DataFrame, fold: WalkForwardFold) -> pd.DataFrame:
    """Drop training trades still open at the start of embargo or evaluation."""
    if not {"entry_at", "closed_at"}.issubset(trades):
        raise ValueError("Trade dates required")
    ent = pd.to_datetime(trades["entry_at"], utc=True)
    close = pd.to_datetime(trades["closed_at"], utc=True)
    boundary = pd.Timestamp(fold.train_end_exclusive_utc)
    train_start = pd.Timestamp(fold.train_start_utc)
    if (close < ent).any():
        raise ValueError("Trade exits before entry")
    return trades.loc[(ent >= train_start) & (close < boundary)].copy()


def fold_manifest(folds: list[WalkForwardFold]) -> list[dict]:
    return [asdict(fold) for fold in folds]
