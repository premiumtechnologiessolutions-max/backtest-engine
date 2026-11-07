"""Design-only multi-family XAUUSD research grid; freeze only with original source.

This module never runs a backtest, labels OOS, opens broker connections, or
uploads the private ZIP. The plan is historical-exposed research only.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
import zipfile
from pathlib import Path
import re

SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
SCHEMA = "NRFX_FROZEN_BATCH_V1"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def parse_years(raw: str) -> tuple[int, ...]:
    if type(raw) is not str or not re.fullmatch(r"20\d{2}(?:,20\d{2})*", raw):
        raise ValueError("Years must be comma-separated YYYY without whitespace")
    years = tuple(int(y) for y in raw.split(","))
    if (len(years) != len(set(years)) or years != tuple(sorted(years))
            or any(not 2010 <= y <= 2026 for y in years)):
        raise ValueError("Years must be unique ascending available 2010–2026")
    return years


def grid(ident: str, name: str, timeframe: str, execution: str, year: int,
         axes: dict[str, list[int | float]]) -> dict:
    return {
        "id_prefix": f"{ident}-{year}", "strategy": name,
        "timeframe": timeframe, "execution": execution,
        "start": f"{year}-01-01", "end": f"{year}-12-31", "grid": axes,
    }


def grids(years: tuple[int, ...]) -> list[dict]:
    if not years or len(years) != len(set(years)) or years != tuple(sorted(years)):
        raise ValueError("Years must be nonempty, unique, and sorted")
    if any(type(y) is not int or not 2010 <= y <= 2026 for y in years):
        raise ValueError("Year outside available historic source")
    output = []
    for year in years:
        output.append(grid("m1sweep", "m1-sweep", "M1", "reference", year, {
            "sweep_lookback": [10, 20, 40, 60],
            "sweep_min_excess_usd": [0.15, 0.30, 0.50],
            "sweep_reclaim_usd": [0.05, 0.10],
            "sweep_stop_buffer_usd": [0.10, 0.20],
            "sweep_reward_risk": [1.0, 1.5, 2.0],
            "sweep_max_stop_usd": [20.0],
        }))
        for tf in ("M15", "H1"):
            output.append(grid(f"tfsweep-{tf.lower()}", "tf-sweep", tf,
                               "reference", year, {
                "tf_sweep_lookback_bars": [8, 12, 20],
                "tf_sweep_penetration_usd": [0.25, 0.50],
                "tf_sweep_stop_buffer_usd": [0.10],
                "tf_sweep_reward_risk": [1.0, 1.5, 2.0],
                "tf_sweep_min_stop_usd": [0.50],
                "tf_sweep_max_stop_usd": [50.0],
            }))
        output.append(grid("bosfib", "bos-fib", "M1", "reference", year, {
            "bos_pivot_left": [3, 5],
            "bos_pivot_right": [3, 5],
            "bos_fib_entry": [0.50, 0.62, 0.705, 0.79, 0.87],
            "bos_zone_lower": [0.50],
            "bos_zone_upper": [0.87],
            "bos_rr": [1.0, 1.5],
            "bos_stop_buffer_usd": [0.10],
            "bos_expiry_minutes": [120],
        }))
        for tf in ("M15", "H1"):
            output.append(grid(f"fvg-{tf.lower()}", "fvg", tf,
                               "reference", year, {
                "fvg_min_gap_usd": [0.50, 1.0],
                "fvg_stop_buffer_usd": [0.10],
                "fvg_rr": [1.5, 2.0],
                "fvg_expiry_hours": [20.0],
            }))
    return output


def count_definitions(items: list[dict]) -> int:
    return sum(math.prod(len(axis) for axis in item["grid"].values()) for item in items)


def make_plan(source: Path, *, years: tuple[int, ...], source_sha256: str,
              engine_commit: str) -> dict:
    if (not isinstance(source, Path) or not source.is_absolute()
            or not source.is_file() or source.is_symlink()):
        raise ValueError("Original private source must be an absolute regular file")
    if (type(source_sha256) is not str or not HEX64.fullmatch(source_sha256)
            or type(engine_commit) is not str or not HEX40.fullmatch(engine_commit)):
        raise ValueError("Full immutable source/engine fingerprints required")
    if source_sha256 != SOURCE_SHA:
        raise ValueError("Unapproved Gold source fingerprint")
    return {
        "schema": SCHEMA, "dataset": str(source),
        "source_sha256": source_sha256,
        "engine_commit": engine_commit,
        "exposure_context": "historical_exposed",
        "jobs": [], "grids": grids(years),
    }


def require_annual_source_members(source: Path, years: tuple[int, ...]) -> None:
    """Fail before freezing if the authorized ZIP lacks a requested annual member.

    Member-name coverage is a necessary preflight, not full quote integrity
    or evidence of continuous observation across every research month.
    """
    if source.suffix.lower() != ".zip" or not zipfile.is_zipfile(source):
        raise ValueError("Authorized original source must be a valid ZIP")
    discovered = {}
    with zipfile.ZipFile(source) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".json"):
                continue
            match = re.search(r"(20\d{2})", Path(name).name)
            if match:
                year = int(match.group(1))
                discovered[year] = discovered.get(year, 0) + 1
    missing = sorted(set(years) - set(discovered))
    duplicates = sorted(y for y in years if discovered.get(y, 0) > 1)
    if missing or duplicates:
        raise ValueError(f"Incomplete or ambiguous original ZIP annual members; missing={missing}, duplicates={duplicates}")


def freeze_plan(source: Path, output: Path, *, years: tuple[int, ...]) -> dict:
    try:
        from scripts import research_batch_orchestrator as batch
    except ModuleNotFoundError as exc:
        if exc.name != "scripts":
            raise
        import research_batch_orchestrator as batch
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("Private plan output parent must already exist and not be a symlink")
    if any(parent.is_symlink() for parent in (output.parent, *output.parent.parents)):
        raise ValueError("Unsafe output parent")
    if source.is_symlink() or not source.is_file() or not source.is_absolute():
        raise ValueError("Source not an authorized absolute private file")
    if batch.file_sha(source) != SOURCE_SHA:
        raise ValueError("Original Gold ZIP SHA256 mismatch: refusing plan")
    if max(years) >= date.today().year:
        raise ValueError("Current or future full-year data cannot yet be complete")
    require_annual_source_members(source, years)
    revision = batch.checkout_commit()
    plan = make_plan(source, years=years, source_sha256=SOURCE_SHA, engine_commit=revision)
    definitions, checksum = batch.expand(plan)
    if len(definitions) != count_definitions(plan["grids"]):
        raise ValueError("Grid expansion count mismatch")
    batch.atomic_manifest(output, plan)
    return {"status": "FROZEN_DESIGN_ONLY_NO_BACKTEST", "defined_jobs": len(definitions),
            "source_sha256": SOURCE_SHA, "plan_sha256": checksum,
            "engine_commit": revision, "plan": str(output)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", default=",".join(str(y) for y in range(2012, 2026)))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    years = parse_years(args.years)
    proposals = grids(years)
    if args.dry_run:
        print(json.dumps({"status": "DEFINED_ONLY_NO_BACKTEST", "years": years,
                          "grid_families": len(proposals),
                          "candidate_definitions": count_definitions(proposals),
                          "max_per_batch_invocation": 500,
                          "not_independent_oos": True}, indent=2))
        return 0
    if args.source is None or args.out is None:
        parser.error("--source and --out required when freezing a private research plan")
    print(json.dumps(freeze_plan(args.source, args.out, years=years), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
