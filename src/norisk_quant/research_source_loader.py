"""Strict local/direct-source lineage gate for B05; never runs trading code."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .data import read_source
from .research_source_preflight import SourcePreflight, preflight_gold_m1_source

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
