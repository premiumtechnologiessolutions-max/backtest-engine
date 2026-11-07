"""Signal-only necessary capacity bound for frozen one-fill-per-signal families.

Use causally generated, pre-execution counts BEFORE SL/TP profitability sweeps.
A non-rejection is NOT evidence of profitable fills or independent OOS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


class PreflightError(ValueError):
    """Insufficient or corrupted pre-execution signal evidence."""


def preflight_signal_capacity(
    by_year: dict[int, pd.DataFrame], *, min_fills_each_year: int,
    rule_columns: tuple[str, ...],
) -> dict:
    """Necessary gate: the SAME frozen parameter ID must have enough signals
    in every required year. Assumes <=1 fill per signal and that risk exits
    do not change signal generation. No fills or P/L are inspected.
    """
    if type(min_fills_each_year) is not int or min_fills_each_year < 1:
        raise PreflightError("min_fills_each_year must be positive native integer")
    if (not isinstance(rule_columns, tuple) or not rule_columns
            or len(rule_columns) != len(set(rule_columns))
            or any(type(c) is not str or not c or c in {"id", "signals", "trades"}
                   for c in rule_columns)):
        raise PreflightError("Invalid signal-rule grouping columns")
    if (not isinstance(by_year, dict) or len(by_year) < 2
            or any(type(y) is not int or not 1900 <= y <= 2200 for y in by_year)):
        raise PreflightError("Require at least two distinct integer calendar years")
    base_ids = None
    base_rules = None
    jointly_possible = None
    summaries = []
    for year in sorted(by_year):
        frame = by_year[year]
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise PreflightError(f"{year}: empty or invalid frozen grid")
        missing = [c for c in ("id", "signals", *rule_columns) if c not in frame]
        if missing:
            raise PreflightError(f"{year}: missing columns {missing}")
        if (frame["id"].isna().any() or not frame["id"].map(
                lambda v: type(v) is str and bool(v.strip())).all()
                or not frame["id"].is_unique):
            raise PreflightError(f"{year}: invalid or duplicate frozen parameter IDs")
        if frame[list(rule_columns)].isna().any().any():
            raise PreflightError(f"{year}: missing signal-rule labels")
        if not frame[list(rule_columns)].apply(
                lambda col: col.map(lambda v: type(v) in (str, int, float)
                                    and (type(v) is not str or bool(v.strip())))).all().all():
            raise PreflightError(f"{year}: invalid signal-rule labels")
        signals = frame["signals"]
        if (not pd.api.types.is_integer_dtype(signals.dtype)
                or pd.api.types.is_bool_dtype(signals.dtype)
                or signals.isna().any() or (signals < 0).any()):
            raise PreflightError(f"{year}: signals must be native nonnegative integers")
        indexed = frame.set_index("id").sort_index()
        rules = indexed[list(rule_columns)]
        if base_ids is None:
            base_ids = set(indexed.index)
            base_rules = rules
        elif set(indexed.index) != base_ids:
            raise PreflightError(f"{year}: frozen parameter IDs differ by year")
        elif not rules.equals(base_rules):
            raise PreflightError(f"{year}: frozen ID-to-rule mapping changed")
        grouped = frame.groupby(list(rule_columns), dropna=False)["signals"].nunique()
        if (grouped != 1).any():
            raise PreflightError(f"{year}: signal count varies across risk-exit variants")
        eligible = set(frame.loc[signals >= min_fills_each_year, "id"])
        jointly_possible = eligible if jointly_possible is None else jointly_possible & eligible
        summaries.append({
            "year": year,
            "correlated_parameter_specs": len(frame),
            "distinct_signal_rule_groups": len(grouped),
            "max_signals_per_spec": int(signals.max()),
            "specs_meeting_necessary_signal_count": len(eligible),
        })
    return {
        "status": ("STRUCTURALLY_UNREACHABLE" if not jointly_possible
                   else "NOT_DISPROVED_BY_SIGNAL_COUNT"),
        "scope": "SIGNAL_ONLY_ONE_FILL_PER_SIGNAL_NECESSARY_GATE_NOT_OOS",
        "min_fills_each_year": min_fills_each_year,
        "correlated_parameter_specs": len(base_ids),
        "same_specs_meeting_signal_gate_in_all_years": len(jointly_possible),
        "years": summaries,
        "warning": ("Sufficient signals cannot establish actual fills, monthly P/L, "
                    "profitability, independence, or prospective validity."),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year-csv", action="append", nargs=2,
                        metavar=("YEAR", "CSV"), required=True)
    parser.add_argument("--min-fills", type=int, required=True)
    parser.add_argument("--rule-columns", nargs="+", required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if len({y for y, _ in args.year_csv}) != len(args.year_csv):
        raise PreflightError("Duplicate year")
    result = preflight_signal_capacity(
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
