"""Pre-backtest signal-capacity upper bound for frozen one-fill-per-signal families.

This is an arithmetic impossibility certificate, NOT a strategy backtest or a
profitability/OOS test. Run on completed, causally generated signal counts
before sweeping risk exits; never use results to retune a frozen hypothesis.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


class SignalCapacityError(ValueError):
    """Malformed or inconsistent signal-count evidence."""


def _strict_counts(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame:
        raise SignalCapacityError(f"Missing {name}")
    values = frame[name]
    if (not pd.api.types.is_integer_dtype(values.dtype)
            or pd.api.types.is_bool_dtype(values.dtype)
            or values.isna().any() or (values < 0).any()):
        raise SignalCapacityError(f"{name} must be native nonnegative integers")
    return values


def audit_signal_capacity(
    by_year: dict[int, pd.DataFrame], *, min_fills_each_year: int,
    rule_columns: tuple[str, ...],
) -> dict:
    """Prove infeasibility when even the *signal* count misses the fill gate.

    Assumptions: every frozen parameter ID has one signal stream, each signal
    can fill at most one position, and risk-exit variants do not change the
    signal stream. The bound cannot certify profitability or feasibility when
    counts reach the threshold; it only proves impossibility when below it.
    """
    if type(min_fills_each_year) is not int or min_fills_each_year < 1:
        raise SignalCapacityError("min_fills_each_year must be positive integer")
    if (not isinstance(rule_columns, tuple) or not rule_columns
            or len(rule_columns) != len(set(rule_columns))
            or any(not isinstance(c, str) or not c or c in {"id", "signals", "trades"}
                   for c in rule_columns)):
        raise SignalCapacityError("Invalid signal-rule grouping columns")
    if (not isinstance(by_year, dict) or len(by_year) < 2
            or any(type(y) is not int or y < 1900 or y > 2200 for y in by_year)):
        raise SignalCapacityError("Require at least two distinct integer calendar years")
    ids = None
    results = []
    for year in sorted(by_year):
        frame = by_year[year]
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise SignalCapacityError(f"{year}: empty or invalid parameter grid")
        required = ("id", "signals", "trades", *rule_columns)
        missing = [col for col in required if col not in frame]
        if missing:
            raise SignalCapacityError(f"{year}: missing columns {missing}")
        if (frame["id"].isna().any() or not frame["id"].map(
                lambda v: isinstance(v, str) and bool(v.strip())).all()
                or not frame["id"].is_unique):
            raise SignalCapacityError(f"{year}: invalid or duplicate parameter IDs")
        counts = _strict_counts(frame, "signals")
        fills = _strict_counts(frame, "trades")
        if (fills > counts).any():
            raise SignalCapacityError(f"{year}: more fills than one-per-event signals")
        if frame[list(rule_columns)].isna().any().any():
            raise SignalCapacityError(f"{year}: missing signal-rule labels")
        # Each risk SL/TP pair shares a signal stream. If its event count
        # changes with SL/TP, this upper bound is not independently valid.
        n_by_rule = frame.groupby(list(rule_columns), dropna=False)["signals"].nunique()
        if (n_by_rule != 1).any():
            raise SignalCapacityError(f"{year}: risk exits changed signal counts")
        current_ids = set(frame["id"])
        if ids is not None and current_ids != ids:
            raise SignalCapacityError(f"{year}: frozen parameter IDs differ by year")
        ids = current_ids
        max_signals = int(counts.max())
        results.append({
            "year": year,
            "parameter_specs": len(frame),
            "signal_rule_groups": len(n_by_rule),
            "nonzero_signal_rule_groups": int((frame.groupby(list(rule_columns))["signals"].max() > 0).sum()),
            "max_signals_per_spec": max_signals,
            "max_actual_fills_per_spec": int(fills.max()),
            "max_possible_fills_less_than_gate": max_signals < min_fills_each_year,
        })
    return {
        "status": "STRUCTURALLY_UNREACHABLE" if any(
            r["max_possible_fills_less_than_gate"] for r in results
        ) else "NOT_DISPROVED_BY_SIGNAL_COUNT",
        "scope": "ONE_FILL_PER_SIGNAL_PREBACKTEST_UPPER_BOUND_NOT_OOS",
        "min_fills_each_year": min_fills_each_year,
        "correlated_parameter_specs": len(ids),
        "years": results,
        "warning": "Counts cannot prove a winning strategy; a feasible bound is not an acceptance pass.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year-csv", action="append", nargs=2, metavar=("YEAR", "CSV"), required=True)
    parser.add_argument("--min-fills", type=int, default=100)
    parser.add_argument("--rule-columns", nargs="+", required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if len({y for y, _ in args.year_csv}) != len(args.year_csv):
        raise SignalCapacityError("Duplicate year")
    result = audit_signal_capacity(
        {int(y): pd.read_csv(path) for y, path in args.year_csv},
        min_fills_each_year=args.min_fills,
        rule_columns=tuple(args.rule_columns),
    )
    output = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
