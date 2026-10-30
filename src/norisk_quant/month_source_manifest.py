"""B07: create a private, one-time Gold M1 source-manifest candidate.

This is an OPERATOR preparation step, never part of worker execution.
It reads only the original local Gold ZIP, creates an immutable-by-content
manifest compatible with B06, and never runs a trading backtest. A candidate
is not proof of pre-registration or provider authenticity. Record its hash
and independently freeze it BEFORE inspecting the subsequent strategy result.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import zipfile

from .data import fingerprint_loaded_m1, load_market, sha256_file, validate_loaded_m1
from .source_registry import register_original_gold_m1, verify_record_manifest
from .research_source_loader import MAX_ZIP_ANNUAL_MEMBER_BYTES

MAX_GOLD_ZIP_BYTES = 2_000_000_000
MAX_EDGE_MINUTES = 4320


@dataclass(frozen=True)
class MonthSourceCandidate:
    manifest: dict
    year: int
    month: int
    rows: int
    first_utc: str
    last_utc: str
    first_unobserved_minutes: int
    last_unobserved_minutes: int

    def public_status(self) -> dict:
        """No file path, original ZIP SHA, price data, account scope or strategy results."""
        return {
            "status": "LOCAL_SOURCE_CANDIDATE_NOT_PREREGISTERED",
            "source_manifest_id": self.manifest["id"],
            "year": self.year, "month": self.month,
            "rows": self.rows,
            "first_utc": self.first_utc,
            "last_utc": self.last_utc,
            "unobserved_start_minutes": self.first_unobserved_minutes,
            "unobserved_end_minutes": self.last_unobserved_minutes,
            "source_authentication": "NOT_VERIFIED",
            "data_rights": "UNVERIFIED",
            "market_closure_classification": "NOT_AUDITED",
            "lineage_type": "DIRECT_ORIGINAL_ZIP_LOCAL_READ",
            "execution": "NONE",
            "independent_oos": False,
            "profitability_verified": False,
            "approved_for_live": False,
        }


def build_month_source_candidate(
    archive: str | Path,
    year: int,
    month: int,
    *,
    observed_now: datetime | None = None,
) -> MonthSourceCandidate:
    """Bounded, fail-closed observed-month source lineage from original archive.

    Both the whole ZIP byte SHA and exact normalized BID+ASK M1 candle SHA
    are calculated independently by canonical import code. Does NOT declare
    the experiment scientifically preregistered; caller freezes before run.
    """
    if type(year) is not int or type(month) is not int or not (2010 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError("Specify a real supported historical UTC month")
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    now = observed_now if observed_now is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("Local time evidence must be explicit UTC")
    if end > now:
        raise ValueError("Cannot freeze a future or still-open historical month")
    src = Path(archive)
    if src.is_symlink() or not src.is_file() or src.suffix.lower() != ".zip":
        raise ValueError("Original market ZIP must be a regular local ZIP file")
    size = src.stat().st_size
    if not 0 < size <= MAX_GOLD_ZIP_BYTES:
        raise ValueError("Original Gold ZIP missing or larger than reviewed capacity")
    try:
        with zipfile.ZipFile(src) as z:
            years = [
                info for info in z.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".json")
                and re.search(r"20\d{2}", Path(info.filename).name)
                and int(re.search(r"20\d{2}", Path(info.filename).name).group(0)) == year
            ]
            if len(years) != 1 or not 0 < years[0].file_size <= MAX_ZIP_ANNUAL_MEMBER_BYTES:
                raise ValueError("Original Gold ZIP requires one bounded JSON annual member")
        bars = validate_loaded_m1(load_market(
            src, start.date().isoformat(),
            (end - timedelta(days=1)).date().isoformat(),
        ))
    except (zipfile.BadZipFile, EOFError) as exc:
        raise ValueError("Original Gold ZIP could not be decompressed") from exc
    if len(bars) < 2:
        raise ValueError("Historical month has insufficient actual observed M1 BID/ASK data")
    first = bars.index[0].to_pydatetime()
    last_end = bars.index[-1].to_pydatetime() + timedelta(minutes=1)
    before = int((first - start).total_seconds() // 60)
    after = int((end - last_end).total_seconds() // 60)
    if not (0 <= before <= MAX_EDGE_MINUTES and 0 <= after <= MAX_EDGE_MINUTES):
        raise ValueError("Unobserved market-month edge exceeds 72-hour review bound")
    # Refuse an archive whose timestamp normalization yielded another year.
    if (bars.index[0].year != year or bars.index[-1].year != year
            or bars.index[0].month != month or bars.index[-1].month != month):
        raise ValueError("Selected original Gold month boundaries do not match request")

    original_sha = sha256_file(src)
    quotes_sha = fingerprint_loaded_m1(bars)
    record = register_original_gold_m1({
        "origin": "user_supplied_gold_m1_bidask",
        "source_file_sha256": original_sha,
        "observed_slice_sha256": quotes_sha,
        "rows": len(bars),
        "first_utc": bars.index[0].isoformat(),
        "last_utc": bars.index[-1].isoformat(),
    })
    manifest = record.internal_manifest()
    if verify_record_manifest(manifest) != record:
        raise ValueError("Original Gold month evidence manifest does not roundtrip")
    return MonthSourceCandidate(
        manifest=manifest, year=year, month=month,
        rows=len(bars), first_utc=record.first_utc, last_utc=record.last_utc,
        first_unobserved_minutes=before,
        last_unobserved_minutes=after,
    )
