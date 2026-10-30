"""Strict local/direct-source lineage gate for B05; never runs trading code."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import re
import zipfile

from .data import read_source, load_market
from .research_source_preflight import (
    SourcePreflight, _canonical_utc, preflight_gold_m1_source,
)

MAX_DIRECT_SOURCE_BYTES = 80_000_000


def preflight_direct_gold_m1_file(proposal: dict, source_manifest: dict, *,
                                  original_m1_file: str | Path,
                                  observed_engine_commit: str) -> SourcePreflight:
    """Independently decode the *same* original JSON/CSV we hash.

    This only proves deterministic direct-source -> loaded-BID/ASK lineage.
    It does not support the user's multi-year ZIP/PARQUET imported lineage;
    that separate importer must prove its source-archive-to-partition mapping.
    """
    path = Path(original_m1_file)
    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {".json", ".csv"}:
        raise ValueError("Direct-source verification supports regular JSON/CSV M1 only")
    if not 0 < path.stat().st_size <= MAX_DIRECT_SOURCE_BYTES:
        raise ValueError("Direct-source M1 file is empty or oversized")
    loaded = read_source(path)
    attested = preflight_gold_m1_source(
        proposal, source_manifest, original_source_file=path,
        normalized_m1=loaded, observed_engine_commit=observed_engine_commit,
    )
    return replace(attested, lineage_verified=True)


MAX_ZIP_ANNUAL_MEMBER_BYTES = 750_000_000
MAX_ZIP_SELECTED_BYTES = 1_500_000_000


def preflight_private_gold_zip_window(
    proposal: dict, source_manifest: dict, *,
    original_gold_zip: str | Path,
    observed_engine_commit: str,
    boundary_tolerance_minutes: int = 0,
) -> SourcePreflight:
    """Replay up to two whole source years from the SAME original ZIP archive.

    The manifest must already be frozen for the exact observed experiment
    window (i.e. 1-2 source years, sliced to the proposal's UTC range).
    Enforce bounded selected ZIP members before decompression. No private
    source data leaves this workstation and no trade/execution occurs.
    """
    path = Path(original_gold_zip)
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".zip":
        raise ValueError("Expected private original Gold ZIP file")
    if not 0 < path.stat().st_size <= 2_000_000_000:
        raise ValueError("Original Gold ZIP size is empty or unsupported")
    start = _canonical_utc(proposal["window_start_utc"])
    end = _canonical_utc(proposal["window_end_exclusive_utc"])
    if start >= end:
        raise ValueError("Reversed private ZIP research window")
    years = tuple(range(start.year, (end - timedelta(microseconds=1)).year + 1))
    if not 1 <= len(years) <= 2:
        raise ValueError("Bounded ZIP source preflight supports one/two years per run")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            chosen = []
            for info in infos:
                if not info.filename.lower().endswith(".json") or info.is_dir():
                    continue
                match = re.search(r"(20\d{2})", Path(info.filename).name)
                if match is not None and int(match.group(1)) in years:
                    if info.file_size <= 0 or info.file_size > MAX_ZIP_ANNUAL_MEMBER_BYTES:
                        raise ValueError("ZIP source year exceeds bounded import limit")
                    chosen.append(info)
            if len(chosen) != len(years) or sum(i.file_size for i in chosen) > MAX_ZIP_SELECTED_BYTES:
                raise ValueError("ZIP research window lacks exactly one bounded JSON per year")
        # Canonical loader itself checks duplicate years, quote consistency,
        # missing required annual members, and complete UTC calendar slicing.
        full = load_market(path, start.date().isoformat(),
                           (end - timedelta(microseconds=1)).date().isoformat())
    except (zipfile.BadZipFile, EOFError) as exc:
        raise ValueError("Damaged original Gold ZIP") from exc
    observed = full.loc[(full.index >= start) & (full.index < end)]
    if observed.empty:
        raise ValueError("No original Gold ZIP BID/ASK bars in frozen window")
    checked = preflight_gold_m1_source(
        proposal, source_manifest, original_source_file=path,
        normalized_m1=observed, observed_engine_commit=observed_engine_commit,
        boundary_tolerance_minutes=boundary_tolerance_minutes,
    )
    return replace(checked, lineage_verified=True)
