"""B05 — read-only source-to-experiment preflight for canonical Gold M1.

A proposal's dataset hash is an assertion until local raw-file and EXACT
loaded BID/ASK M1 hashes are independently calculated. This module
cross-checks those identifiers and the observed UTC range, then produces
an untrusted-source binding *candidate*. It never runs strategy logic,
executes orders, changes a frozen research protocol, or certifies P/L/OOS.

A source archive and a separate preloaded M1 frame can each be hashed without
proof that the latter was created from that archive. A future importer lineage
gate must prove that relationship on original private data before executing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import pandas as pd

from .data import (
    fingerprint_loaded_m1, quality, sha256_file, validate_loaded_m1,
)
from .research_control_plane import proposal_identity
from .source_registry import SourceRecord, verify_record_manifest

HEX40 = re.compile(r"[a-f0-9]{40}\Z")


def _canonical_utc(value: str) -> datetime:
    if type(value) is not str or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)\Z", value
    ):
        raise ValueError("Evidence window must be explicit UTC")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid UTC evidence window") from exc
    if dt.utcoffset() != timedelta(0):
        raise ValueError("Non-UTC evidence window")
    return dt.astimezone(timezone.utc)


def inspect_local_checkout(root: str | Path) -> str:
    """Inspect exact tracked Git HEAD without mutating the operator checkout.

    A clean tracked worktree is necessary, not a comprehensive proof of
    dependencies or untracked third-party execution. No strategies run here.
    """
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Expected a real Git checkout directory")

    def git(*args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *args],
                check=True, capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Unable to inspect local Git research checkout") from exc
        return result.stdout.strip()

    exact_root = git("rev-parse", "--show-toplevel")
    if Path(exact_root).resolve() != root.resolve():
        raise ValueError("Expected exact top-level Git research checkout")
    head = git("rev-parse", "HEAD")
    if not HEX40.fullmatch(head):
        raise ValueError("Unpinned research Git commit")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Canonical research checkout has modified tracked files")
    return head


@dataclass(frozen=True)
class SourcePreflight:
    experiment_id: str
    source_manifest_id: str
    observed_m1_sha256: str
    source_sha256: str
    engine_commit: str
    rows: int
    first_utc: str
    last_utc: str
    execution: str = "NONE"
    provenance_level: str = "LOCAL_HASHES_MATCH_DECLARED_SOURCE"
    data_rights: str = "UNVERIFIED"
    lineage_verified: bool = False
    source_authentication: str = "NOT_VERIFIED"
    gaps_audited: bool = False
    strategy_implementation_verified: bool = False
    broker_fill_parity: bool = False
    independent_oos: bool = False
    profitability_verified: bool = False
    approved_for_live: bool = False

    def public_metadata(self) -> dict[str, Any]:
        """No source bytes, private paths, quote arrays or untrusted hashes."""
        return {
            "experiment_id": self.experiment_id,
            "source_manifest_id": self.source_manifest_id,
            "rows": self.rows, "first_utc": self.first_utc,
            "last_utc": self.last_utc,
            "execution": self.execution,
            "provenance_level": self.provenance_level,
            "data_rights": self.data_rights,
            "lineage_verified": self.lineage_verified,
            "source_authentication": self.source_authentication,
            "gaps_audited": False,
            "strategy_implementation_verified": False,
            "broker_fill_parity": False,
            "independent_oos": False, "profitability_verified": False,
            "approved_for_live": False,
        }


def preflight_gold_m1_source(
    proposal: dict, source_manifest: dict, *,
    original_source_file: str | Path,
    normalized_m1: pd.DataFrame,
    observed_engine_commit: str,
    boundary_tolerance_minutes: int = 0,
) -> SourcePreflight:
    """Check exact source bytes and Bid/Ask frame, then stage non-executable proof.

    No caller-controlled "verified" flags are accepted. This does NOT prove
    that the M1 frame was derived from the separately supplied archive;
    that requires a source-import lineage audit on the private workstation.
    """
    job_id, _, _ = proposal_identity(proposal)
    record: SourceRecord = verify_record_manifest(source_manifest)
    if (record.family != "original_gold_m1_bidask"
            or record.source_claim != "ORIGINAL_M1_DECLARED"
            or record.asset != "XAUUSD"
            or record.instrument != "XAUUSD"
            or record.account_currency is not None
            or record.execution != "NONE"
            or record.independent_oos is not False):
        raise ValueError("Only original non-executable Gold M1 source is eligible")
    if proposal["dataset_sha256"] != record.source_file_sha256:
        raise ValueError("Proposal is not bound to original M1 file SHA")
    if type(observed_engine_commit) is not str or not HEX40.fullmatch(observed_engine_commit):
        raise ValueError("Original engine Git commit must be exact SHA")
    if proposal["engine_commit"] != observed_engine_commit:
        raise ValueError("Local research checkout differs from frozen experiment")

    path = Path(original_source_file)
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Original research data must be a nonempty regular local file")
    actual_source_sha = sha256_file(path)
    if actual_source_sha != record.source_file_sha256:
        raise ValueError("Original market source bytes differ from frozen manifest")

    # canonical validates BID/ASK, OHLC coherence, timestamp order, and no
    # duplicates. Never synthesize missing minute bars or infer event order.
    verified_m1 = validate_loaded_m1(normalized_m1.copy())
    if len(verified_m1) != record.rows:
        raise ValueError("Exact observed M1 row count does not match source manifest")
    if (verified_m1.index[0].isoformat() != record.first_utc
            or verified_m1.index[-1].isoformat() != record.last_utc):
        raise ValueError("Observed M1 UTC boundary does not match source manifest")
    observed_m1_sha = fingerprint_loaded_m1(verified_m1)
    if observed_m1_sha != record.observed_quote_sha256:
        raise ValueError("Original observed BID/ASK quote fingerprint changed")

    start = _canonical_utc(proposal["window_start_utc"])
    end = _canonical_utc(proposal["window_end_exclusive_utc"])
    # A calendar month can start/end during a weekend or holiday. Do not
    # fabricate bars or certify a gap as a closure. Bounded tolerance applies
    # ONLY to the unobserved *outer edges* of the requested UTC interval.
    # Default 0 maintains the strict B05 public preflight contract.
    if (type(boundary_tolerance_minutes) is not int
            or not 0 <= boundary_tolerance_minutes <= 4320):
        raise ValueError("Invalid bounded calendar-edge tolerance")
    first = verified_m1.index[0].to_pydatetime()
    last_end = verified_m1.index[-1].to_pydatetime() + timedelta(minutes=1)
    tolerance = timedelta(minutes=boundary_tolerance_minutes)
    if start < first and first - start > tolerance:
        raise ValueError("Requested historical start is before the available M1 source")
    if end > last_end and end - last_end > tolerance:
        raise ValueError("Requested historical end uses unobserved future M1 data")
    if not ((verified_m1.index >= pd.Timestamp(start))
            & (verified_m1.index < pd.Timestamp(end))).any():
        raise ValueError("Historical experiment contains no observed M1 bars")

    first = verified_m1.index[0].isoformat()
    last = verified_m1.index[-1].isoformat()
    # Data quality is measurable, but missing minutes may be legitimate
    # exchange/weekend closures. The future gap classifier must adjudicate.
    _ = quality(verified_m1)
    return SourcePreflight(
        experiment_id=job_id, source_manifest_id=record.id,
        observed_m1_sha256=observed_m1_sha, source_sha256=actual_source_sha,
        engine_commit=observed_engine_commit,
        rows=len(verified_m1), first_utc=first, last_utc=last,
    )
