"""Fail-closed arithmetic and frozen-acceptance audit of FAC020 CSV exports.

No market data, no strategy search, no parameter tuning. Correlated specs != independent hypotheses.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
import zipfile
from collections import Counter
from pathlib import Path

MONTHS = tuple(f"m{i:02d}" for i in range(1, 13))
GATE = ("months", "fills", "both_years", "worst_month", "floating_dd")


def _number(row, field):
    x = float(row[field])
    if not math.isfinite(x):
        raise ValueError(f"Nonfinite {field}")
    return x


def _close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-7)


def _index(rows):
    result = {}
    for row in rows:
        key = row.get("id", "")
        if not key or key in result:
            raise ValueError("Missing or duplicated candidate id")
        result[key] = row
    if not result:
        raise ValueError("Empty candidate export")
    return result


def audit(annual_2012, annual_2013, combined):
    a, b, c = map(_index, (annual_2012, annual_2013, combined))
    if not (a.keys() == b.keys() == c.keys()):
        raise ValueError("Candidate ID mismatch across years and combined export")
    failures = Counter()
    gates = Counter()
    max_months = -1
    passed = 0
    rule_ids = set()
    high_month_ids = []
    for key, row in c.items():
        y1, y2 = a[key], b[key]
        for y in (y1, y2):
            if y.get("rule_id") != row.get("rule_id"):
                raise ValueError(f"Rule ID mismatch: {key}")
            monthly = [_number(y, m) for m in MONTHS]
            net = _number(y, "net_usd_oz")
            trades = _number(y, "trades")
            fees = _number(y, "fees_usd")
            if trades < 0 or not trades.is_integer() or not _close(net, sum(monthly)) or not _close(fees, 0.4 * trades):
                raise ValueError(f"Annual monthly/fee/trade invariant: {key}")
            if _number(y, "max_m1_dd") < 0:
                raise ValueError(f"Negative floating drawdown: {key}")
        m1 = [_number(y1, m) for m in MONTHS]
        m2 = [_number(y2, m) for m in MONTHS]
        months = sum(v > 0 for v in m1 + m2)
        worst = min(m1 + m2)
        dd = max(_number(y1, "max_m1_dd"), _number(y2, "max_m1_dd"))
        expected = {
            "net_2012": _number(y1, "net_usd_oz"),
            "net_2013": _number(y2, "net_usd_oz"),
            "net_total": _number(y1, "net_usd_oz") + _number(y2, "net_usd_oz"),
            "worst_month": worst,
            "max_annual_floating_dd": dd,
            "trades_2012": _number(y1, "trades"),
            "trades_2013": _number(y2, "trades"),
            "fees_total": _number(y1, "fees_usd") + _number(y2, "fees_usd"),
            "positive_months": months,
        }
        for field, value in expected.items():
            if not _close(_number(row, field), value):
                raise ValueError(f"Combined {field} mismatch: {key}")
        conditions = {
            "months": months >= 18,
            "fills": expected["trades_2012"] >= 100 and expected["trades_2013"] >= 100,
            "both_years": expected["net_2012"] > 0 and expected["net_2013"] > 0,
            "worst_month": worst >= -20,
            "floating_dd": dd <= 100,
        }
        for name, value in conditions.items():
            gates[name] += bool(value)
        pattern = ",".join(name for name in GATE if not conditions[name]) or "PASS"
        failures[pattern] += 1
        qualifies = all(conditions.values())
        if str(row.get("passed", "")).lower() != str(qualifies).lower():
            raise ValueError(f"Frozen acceptance mismatch: {key}")
        passed += qualifies
        rule_ids.add(row["rule_id"])
        max_months = max(max_months, months)
        if months >= 18:
            high_month_ids.append(key)
    return {
        "status": "AUDIT_ONLY_NO_NEW_BACKTESTS",
        "distinct_correlated_parameter_specs": len(c),
        "distinct_entry_rule_groups_not_independent_hypotheses": len(rule_ids),
        "annual_replays_reconciled": len(a) + len(b),
        "monthly_values_reconciled": 12 * (len(a) + len(b)),
        "max_positive_months": max_months,
        "specs_with_at_least_18_positive_months": len(high_month_ids),
        "specs_passing_frozen_joint_gate": passed,
        "individual_gate_pass_counts": dict(gates),
        "joint_failure_patterns": dict(sorted(failures.items())),
        "high_month_spec_ids": sorted(high_month_ids),
        "warning": "Historically exposed 2012/2013. No forward OOS, no portfolio aggregation, no retuning.",
    }


def read_archive(path):
    with zipfile.ZipFile(path) as z:
        names = ("FAC020_2012/all_candidates_monthly.csv",
                 "FAC020_2013/all_candidates_monthly.csv",
                 "FAC020_COMBINED_12288.csv")
        return [list(csv.DictReader(io.StringIO(z.read(name).decode("utf-8")))) for name in names]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fac020-export-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refuse to overwrite prior audit")
    result = audit(*read_archive(args.fac020_export_zip))
    if result["distinct_correlated_parameter_specs"] != 12288 or result["specs_passing_frozen_joint_gate"] != 0:
        raise ValueError("Unexpected FAC020 frozen export shape or acceptance result")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
