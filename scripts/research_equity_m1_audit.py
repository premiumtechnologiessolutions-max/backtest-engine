"""Strict offline audit of canonical observed M1 equity; no inferred minutes or trades.

Optional evidence verifier, NOT a backtest runner, OOS certificate, portfolio
simulator, or substitute for an independently frozen equity hash.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import subprocess

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
FIELDS = ("at", "realized_pnl", "floating_pnl", "equity", "drawdown")


def _regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or symlinked evidence")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Nonregular or hardlinked evidence")


def _hash(path: Path) -> str:
    _regular(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict:
    _regular(path)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON evidence key")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("Nonfinite JSON evidence")
    def finite_float(token):
        number = float(token)
        if not math.isfinite(number):
            raise ValueError("Nonfinite JSON evidence")
        return number
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=unique,
                          parse_constant=invalid_constant, parse_float=finite_float)
    if type(value) is not dict:
        raise ValueError("Invalid JSON evidence object")
    return value


def _float(value: object) -> float:
    if type(value) not in (str, int, float):
        raise ValueError("Invalid evidence numeric type")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Invalid evidence number") from exc
    if not math.isfinite(number):
        raise ValueError("Nonfinite evidence number")
    return number


def _count(value: object) -> int:
    if type(value) is int and value >= 0:
        return value
    if type(value) is str and re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
        return int(value)
    raise ValueError("Invalid observed M1 count")


def _same(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-6


def _timestamp(value: str) -> datetime:
    if type(value) is not str:
        raise ValueError("Invalid M1 timestamp")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid M1 timestamp") from exc
    if (timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp)
            or timestamp.second or timestamp.microsecond):
        raise ValueError("M1 timestamp must be exact UTC minute")
    return timestamp


def _csv(path: Path, required: set[str]):
    _regular(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        names = reader.fieldnames
        if (not names or len(names) != len(set(names))
                or any(not name or name.strip() != name for name in names)
                or not required.issubset(names)):
            raise ValueError("Missing or duplicate CSV evidence columns")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Ragged CSV evidence")
            yield row


def audit_equity(run: Path, archive: Path, source_sha: str,
                 engine_sha: str, expected_hashes: dict[str, str]) -> dict:
    """Reconcile each observed M1 mark to externally pinned canonical evidence.

    A hash supplied by calculating it from the same untrusted file is not an
    independent attestation. Private archive bytes never enter the output.
    """
    if (type(source_sha) is not str or not HEX64.fullmatch(source_sha)
            or type(engine_sha) is not str or not HEX40.fullmatch(engine_sha)):
        raise ValueError("Invalid frozen source or engine SHA")
    if (type(expected_hashes) is not dict or set(expected_hashes) !=
            {"summary.json", "monthly.csv", "equity_m1.csv"}
            or any(type(v) is not str or not HEX64.fullmatch(v)
                   for v in expected_hashes.values())):
        raise ValueError("Three independently pinned evidence hashes required")
    run, archive = Path(run), Path(archive)
    if run.is_symlink() or not run.is_dir():
        raise ValueError("Unsafe canonical run directory")
    if _hash(archive) != source_sha:
        raise ValueError("Private original archive SHA mismatch")
    for name, digest in expected_hashes.items():
        if _hash(run / name) != digest:
            raise ValueError("Frozen evidence SHA mismatch: " + name)
    summary = _json(run / "summary.json")
    provenance = summary.get("source_fingerprints")
    if (summary.get("execution") != "synthetic_same_reference_bid_ohlc_fixed_all_in_fee"
            or type(provenance) is not dict
            or provenance.get("source_file_sha256") != source_sha
            or provenance.get("git_revision_env") != engine_sha
            or type(summary.get("settings")) is not dict
            or type(summary.get("start_utc")) is not str
            or type(summary.get("end_utc")) is not str
            or type(summary["settings"].get("roundtrip_cost_per_ounce")) not in (int, float)
            or _float(summary["settings"].get("roundtrip_cost_per_ounce")) != 0.40):
        raise ValueError("Canonical source/code/cost evidence mismatch")
    monthly = list(_csv(run / "monthly.csv", {"period", "observed_m1_samples",
                                            "month_end_equity", "month_end_drawdown"}))
    if not monthly or _count(summary.get("months_observed")) != len(monthly):
        raise ValueError("Incomplete canonical monthly ledger")
    labels = [row["period"] for row in monthly]
    if (labels != sorted(labels) or len(set(labels)) != len(labels)
            or any(not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", x) for x in labels)):
        raise ValueError("Invalid canonical monthly ordering")
    totals = {label: {"count": 0, "last": None, "max_dd": 0.0,
                      "gap_events": 0} for label in labels}
    previous = None
    first_stamp = None
    peak = 0.0
    max_dd = 0.0
    last_realized = None
    count = 0
    for row in _csv(run / "equity_m1.csv", set(FIELDS)):
        stamp = _timestamp(row["at"])
        if first_stamp is None:
            first_stamp = stamp
        if previous is not None:
            gap = (stamp - previous).total_seconds()
            if gap < 60 or gap % 60:
                raise ValueError("Nonmonotonic or non-M1 canonical timestamps")
        month = stamp.strftime("%Y-%m")
        if month not in totals:
            raise ValueError("M1 timestamp outside canonical monthly ledger")
        current = totals[month]
        if previous is not None and gap > 60:
            current["gap_events"] += 1  # Never fabricate missing minutes.
        realized = _float(row["realized_pnl"])
        floating = _float(row["floating_pnl"])
        equity = _float(row["equity"])
        reported_dd = _float(row["drawdown"])
        if not _same(realized + floating, equity):
            raise ValueError("Realized plus floating does not equal equity")
        peak = max(peak, equity)
        dd = max(0.0, peak - equity)
        if not _same(dd, reported_dd):
            raise ValueError("M1 peak drawdown arithmetic mismatch")
        current["count"] += 1
        current["last"] = equity
        current["max_dd"] = max(current["max_dd"], dd)
        max_dd = max(max_dd, dd)
        last_realized = realized
        previous = stamp
        count += 1
    if not count:
        raise ValueError("Empty canonical M1 equity")
    if _timestamp(summary["start_utc"]) != first_stamp:
        raise ValueError("Canonical first M1 timestamp mismatch")
    if _timestamp(summary["end_utc"]) != previous:
        raise ValueError("Canonical last M1 timestamp mismatch")
    month_peak = 0.0
    output = []
    for row in monthly:
        month = row["period"]
        item = totals[month]
        if not item["count"] or item["count"] != _count(row["observed_m1_samples"]):
            raise ValueError("M1 samples disagree with canonical month")
        if not _same(item["last"], _float(row["month_end_equity"])):
            raise ValueError("M1 month-end equity mismatch")
        month_peak = max(month_peak, item["last"])
        if not _same(month_peak - item["last"], _float(row["month_end_drawdown"])):
            raise ValueError("M1 month-end drawdown mismatch")
        output.append({
            "month_utc": month,
            "observed_m1_samples": item["count"],
            "max_observed_m1_global_peak_drawdown_usd_per_oz": round(item["max_dd"], 8),
            "last_observed_equity_usd_per_oz": round(item["last"], 8),
            "observed_gap_events_from_prior_mark": item["gap_events"],
        })
    if (not _same(max_dd, _float(summary.get("max_drawdown_observed_m1")))
            or not _same(totals[labels[-1]]["last"], _float(summary.get("last_observed_equity")))
            or not _same(last_realized, _float(summary.get("last_observed_realized_pnl")))):
        raise ValueError("M1 floating risk disagrees with canonical summary")
    return {
        "status": "HASH_PINNED_OBSERVED_M1_RECONCILED_HISTORICAL_NOT_OOS",
        "source_sha256": source_sha, "engine_commit": engine_sha,
        "evidence_sha256": dict(expected_hashes),
        "observed_m1_samples": count,
        "max_observed_m1_global_peak_drawdown_usd_per_oz": round(max_dd, 8),
        "monthly": output,
        "missing_minutes_filled": 0,
        "shared_capacity_verified": False,
        "clean_prospective_oos": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--private-archive", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--engine-commit", required=True)
    for name in ("summary", "monthly", "equity-m1"):
        parser.add_argument("--" + name + "-sha256", required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                              check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                               cwd=root, check=True, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Cannot verify canonical Git checkout") from exc
    if head != args.engine_commit or dirty.strip():
        raise ValueError("Dirty or mismatched canonical Git checkout")
    try:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", "src", "scripts"],
            cwd=root, check=True, capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Cannot verify untracked canonical source") from exc
    if untracked.strip():
        raise ValueError("Untracked canonical source invalidates frozen checkout")
    result = audit_equity(args.run, args.private_archive, args.source_sha256,
                          args.engine_commit, {
                              "summary.json": args.summary_sha256,
                              "monthly.csv": args.monthly_sha256,
                              "equity_m1.csv": args.equity_m1_sha256,
                          })
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
