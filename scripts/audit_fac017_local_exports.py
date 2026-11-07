"""Independent arithmetic/provenance audit of FAC017 local CSV exports.

No private BID/ASK source required. This is NOT canonical M1 execution parity.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

MONTHS = [f"m{i:02d}" for i in range(1, 13)]
LOOKBACKS = (12, 20, 32, 48)
SHOCKS = (1.25, 1.50, 2., 2.50)
RETRACES = (.25, .40, .55)
REGIMES = ("QUIET", "ACTIVE")
SESSIONS = ("ALL", "LONDON_LOCAL_08_12", "NY_LOCAL_0930_1330")
MULTS = tuple(.50 + .25 * i for i in range(8))
EXPECTED_SPECS = 18_432
YEAR_METRICS = ("trades", "net_usd_oz", "max_m1_dd", "worst_month", "positive_months", "fees_usd")


def _require(ok: bool, message: str) -> None:
    if not bool(ok):
        raise ValueError(message)


def _close(actual, expected, label: str) -> None:
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    _require(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all()
             and np.allclose(a, b, rtol=0, atol=1e-7), label)


def _ids(table: pd.DataFrame) -> pd.Series:
    return table.apply(lambda r: (
        f"VSE17_N{int(r.lookback):02d}_Q{r.shock:.2f}_R{r.retrace:.2f}_"
        f"{r.regime}_{r.session}_SL{r.stop_mult:.2f}_TP{r.target_mult:.2f}"
    ), axis=1)


def _annual(table: pd.DataFrame, year: int, full: bool) -> pd.DataFrame:
    required = {"id", "lookback", "shock", "retrace", "regime", "session", "stop_mult",
                "target_mult", "signals", "expired", "trades", "net_usd_oz", "fees_usd",
                "max_m1_dd", "positive_months", "worst_month", *MONTHS}
    _require(required.issubset(table.columns), f"{year}: missing columns")
    _require(table.id.notna().all() and table.id.is_unique, f"{year}: duplicate/missing IDs")
    _require(not table.empty, f"{year}: empty export")
    if full:
        _require(len(table) == EXPECTED_SPECS, f"{year}: incomplete frozen grid")
    for col, allowed in (("lookback", LOOKBACKS), ("shock", SHOCKS),
                         ("retrace", RETRACES), ("regime", REGIMES),
                         ("session", SESSIONS), ("stop_mult", MULTS),
                         ("target_mult", MULTS)):
        _require(table[col].isin(allowed).all(), f"{year}: nonfrozen {col}")
    _require(table.id.eq(_ids(table)).all(), f"{year}: parameter ID mismatch")
    if full:
        frozen_ids = {
            f"VSE17_N{n:02d}_Q{q:.2f}_R{r:.2f}_{g}_{s}_SL{sl:.2f}_TP{tp:.2f}"
            for n, q, r, g, s, sl, tp in itertools.product(
                LOOKBACKS, SHOCKS, RETRACES, REGIMES, SESSIONS, MULTS, MULTS)
        }
        _require(set(table.id) == frozen_ids, f"{year}: frozen grid IDs differ")
    for col in ("signals", "expired", "trades", "positive_months"):
        v = table[col].to_numpy(dtype=float)
        _require(np.isfinite(v).all() and (v >= 0).all() and (v == np.floor(v)).all(),
                 f"{year}: invalid count {col}")
    _require((table.trades <= table.signals).all() and
             (table.trades + table.expired <= table.signals).all(),
             f"{year}: impossible signal accounting")
    m = table[MONTHS].to_numpy(dtype=float)
    _require(np.isfinite(m).all(), f"{year}: nonfinite monthly P/L")
    _close(table.net_usd_oz, m.sum(axis=1), f"{year}: monthly P/L mismatch")
    _close(table.fees_usd, .40 * table.trades, f"{year}: all-in fee mismatch")
    _close(table.worst_month, m.min(axis=1), f"{year}: worst month mismatch")
    _close(table.positive_months, (m > 0).sum(axis=1), f"{year}: positive month mismatch")
    _require(np.isfinite(table.max_m1_dd).all() and (table.max_m1_dd >= 0).all(),
             f"{year}: invalid floating drawdown")
    _require((table.loc[table.trades == 0, "net_usd_oz"].abs() <= 1e-7).all(),
             f"{year}: zero-trade nonzero net")
    return table.set_index("id")


def audit(year_2012: Path, year_2013: Path, combined: Path, *, full=True) -> dict:
    a = _annual(pd.read_csv(year_2012), 2012, full)
    b = _annual(pd.read_csv(year_2013), 2013, full)
    c = pd.read_csv(combined)
    _require(c.id.notna().all() and c.id.is_unique, "combined duplicate/missing IDs")
    _require(set(a.index) == set(b.index) == set(c.id), "annual/combined ID mismatch")
    c = c.set_index("id").loc[a.index]
    b = b.loc[a.index]
    for year, frame in ((2012, a), (2013, b)):
        for col in YEAR_METRICS:
            _close(c[f"{col}_{year}"], frame[col], f"combined {year} {col} mismatch")
    pos = a.positive_months + b.positive_months
    net = a.net_usd_oz + b.net_usd_oz
    worst = np.minimum(a.worst_month, b.worst_month)
    dd = np.maximum(a.max_m1_dd, b.max_m1_dd)
    for name, expected in (("positive_24", pos), ("net_24", net),
                           ("worst_24", worst), ("max_annual_dd", dd)):
        _close(c[name], expected, f"combined {name} mismatch")
    _require(c.fills_both.eq((a.trades >= 100) & (b.trades >= 100)).all(),
             "combined frozen minimum-fills gate mismatch")
    gate = ((a.trades >= 100) & (b.trades >= 100) & (pos >= 18) &
            (a.net_usd_oz > 0) & (b.net_usd_oz > 0) &
            (worst >= -20) & (dd <= 100))
    _require(c.gate.eq(gate).all(), "combined frozen joint gate mismatch")
    return {
        "status": "ARITHMETIC_ONLY_OFFICIAL_CANONICAL_PENDING",
        "distinct_correlated_specs": len(c),
        "annual_executions": len(a) + len(b),
        "active_annual_replays": int((a.trades > 0).sum() + (b.trades > 0).sum()),
        "zero_trade_annual_replays": int((a.trades == 0).sum() + (b.trades == 0).sum()),
        "monthly_values_including_zeros": 12 * (len(a) + len(b)),
        "positive_months_max_of_24": int(pos.max()),
        "configs_24_of_24": int((pos == 24).sum()),
        "configs_at_least_18_of_24": int((pos >= 18).sum()),
        "configs_positive_net_both_years": int(((a.net_usd_oz > 0) & (b.net_usd_oz > 0)).sum()),
        "configs_passing_frozen_joint_gate": int(gate.sum()),
        "canonical_parity_verified": False,
        "new_backtests_executed_by_this_audit": 0,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--year-2012", type=Path, required=True)
    p.add_argument("--year-2013", type=Path, required=True)
    p.add_argument("--combined", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(audit(args.year_2012, args.year_2013, args.combined), indent=2))


if __name__ == "__main__":
    main()
