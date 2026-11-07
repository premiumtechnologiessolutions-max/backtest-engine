"""FAC024 canonical CSV adapter: bind parsed M1 quotes to hashed source bytes.

This opt-in adapter is for a *strictly specified* UTF-8 CSV format, not
arbitrary broker exports. It cannot authenticate a broker or timestamp.
No quote data is uploaded; only the returned metadata may be shared.
"""
from __future__ import annotations

import csv
from hashlib import sha256
from io import StringIO
from pathlib import Path
import re

import pandas as pd

from .prospective_manifest import register_closed_month

_HEADER = ("at", "o", "h", "l", "c", "ao", "ah", "al", "ac")
_UTC_M1 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z\Z")
_DECIMAL = re.compile(r"(?:0|[1-9]\d*)(?:\.\d+)?\Z")


def register_closed_month_csv(
    month: str,
    path: str | Path,
    *,
    registered_at_utc: object,
    as_of_utc: object,
) -> dict:
    """Register the exact file bytes used to parse the observed M1 DataFrame.

    Contract: UTF-8 CSV, exact nine-column header, ISO UTC minute timestamps
    ending in Z, plain nonnegative decimal quote text (no exponent/NaN/Inf),
    one M1 observation per row. The common prospective validator additionally
    enforces strictly positive valid BID/ASK candles, UTC order and month bounds.

    Read the original file into one immutable byte buffer. The parsed frame is
    derived exclusively from that buffer, then the normal registration hashes
    the path again. Require identical SHA256 and size to detect file changes
    between reading and registration. This does NOT certify external provenance,
    market completeness, or a trusted registration clock.
    """
    source = Path(path)
    raw = source.read_bytes()
    if not raw:
        raise ValueError("Empty FAC024 CSV source")
    source_digest = sha256(raw).hexdigest()
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("FAC024 CSV must be UTF-8") from exc
    if "\x00" in decoded:
        raise ValueError("FAC024 CSV contains NUL bytes")

    reader = csv.reader(StringIO(decoded, newline=""), strict=True)
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("FAC024 CSV has no header") from exc
    if tuple(header) != _HEADER:
        raise ValueError("FAC024 CSV requires exact ordered unique header")

    dates: list[str] = []
    prices: list[list[float]] = []
    try:
        for line, row in enumerate(reader, start=2):
            if len(row) != len(_HEADER):
                raise ValueError(f"FAC024 CSV row {line} must have nine fields")
            if not _UTC_M1.fullmatch(row[0]):
                raise ValueError(f"FAC024 CSV row {line} requires canonical UTC M1 timestamp")
            if any(not _DECIMAL.fullmatch(value) for value in row[1:]):
                raise ValueError(f"FAC024 CSV row {line} requires plain decimal quotes")
            dates.append(row[0])
            prices.append([float(value) for value in row[1:]])
    except csv.Error as exc:
        raise ValueError("Malformed FAC024 CSV quoting") from exc
    if not dates:
        raise ValueError("FAC024 CSV contains no M1 observations")

    try:
        index = pd.DatetimeIndex(pd.to_datetime(
            dates, format="%Y-%m-%dT%H:%M:%SZ", utc=True, errors="raise"
        ))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("FAC024 CSV has invalid UTC M1 dates") from exc
    observed = pd.DataFrame(prices, columns=list(_HEADER[1:]), index=index)
    record = register_closed_month(
        month, source, observed,
        registered_at_utc=registered_at_utc,
        as_of_utc=as_of_utc,
    )
    if (record["source_sha256"] != source_digest
            or record["source_bytes"] != len(raw)):
        raise ValueError("FAC024 CSV source changed between parsing and registration")
    return record
