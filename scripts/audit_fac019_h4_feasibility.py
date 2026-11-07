"""FAC019 pre-execution structural H4 capacity audit; never measures P/L.

Only aggregate counts leave the private environment. Frozen FAC019 requires
eight consecutive complete H4 bars, never bridged across market closures.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED = 8
ORIGINAL_SHA256 = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"


def h4_capacity(h4: pd.DataFrame) -> dict:
    """Count genuine contiguous H4 windows using completed UTC bars only."""
    idx = h4.index
    if not isinstance(idx, pd.DatetimeIndex) or idx.tz is None or str(idx.tz) != "UTC":
        raise ValueError("H4 index must be timezone-aware UTC")
    if not idx.is_monotonic_increasing or not idx.is_unique:
        raise ValueError("H4 timestamps must be strictly increasing")
    if "close_at" not in h4:
        raise ValueError("H4 close_at missing")
    close_at = pd.DatetimeIndex(pd.to_datetime(h4["close_at"], utc=True))
    if not close_at.equals(idx + pd.Timedelta(hours=4)):
        raise ValueError("H4 bars must close exactly four hours after UTC open")
    if len(idx) and not (idx == idx.floor("4h")).all():
        raise ValueError("H4 open must align to UTC four-hour boundaries")
    if len(idx) == 0:
        return {"complete_h4_bars": 0, "max_consecutive_h4_bars": 0,
                "eligible_eight_bar_windows": 0, "can_form_frozen_context": False}
    gap = np.flatnonzero(np.diff(idx.asi8) != 14_400_000_000_000) + 1
    lengths = np.diff(np.r_[0, gap, len(idx)])
    windows = int(np.maximum(lengths - REQUIRED + 1, 0).sum())
    return {"complete_h4_bars": len(idx),
            "max_consecutive_h4_bars": int(lengths.max()),
            "eligible_eight_bar_windows": windows,
            "can_form_frozen_context": windows > 0}


def audit_private_source(gold_zip: Path, years=(2012, 2013)) -> dict:
    """Run locally on SHA-verified ZIP; output aggregate feasibility only."""
    from norisk_quant.data import load_market, sha256_file
    from norisk_quant.strategy import aggregate_bars
    if sha256_file(gold_zip) != ORIGINAL_SHA256:
        raise ValueError("Original private ZIP SHA256 mismatch")
    if tuple(years) != (2012, 2013):
        raise ValueError("FAC019 frozen design years are 2012 and 2013")
    result = {}
    for year in years:
        m1 = load_market(gold_zip, f"{year}-01-01", f"{year}-12-31")
        result[str(year)] = h4_capacity(aggregate_bars(m1, "H4"))
    impossible = any(not r["can_form_frozen_context"] for r in result.values())
    return {"research_id": "NRF-FAC-019",
            "status": "STRUCTURALLY_UNREACHABLE" if impossible else "H4_GATE_FEASIBLE_ONLY",
            "preregistration_commit": "530fc65c24d16b1733543f7bf7eceafb5b411542",
            "source_sha256": ORIGINAL_SHA256, "required_consecutive_h4": REQUIRED,
            "years": result, "executed_annual_backtests": 0,
            "observed_monthly_pnl": 0, "canonical_parity_samples": 0,
            "note": "Necessary context gate only; no profitability, fills, or OOS claim."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("Refuse to overwrite existing audit output")
    report = audit_private_source(args.gold_zip)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
