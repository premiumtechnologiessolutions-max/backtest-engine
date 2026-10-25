from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

RAW_COLUMNS = ("ts", "o", "h", "l", "c", "ao", "ah", "al", "ac")
PRICE_COLUMNS = ("o", "h", "l", "c", "ao", "ah", "al", "ac")


def normalize(raw: pd.DataFrame, *, strict: bool = True) -> pd.DataFrame:
    """Normalize original gold BID/ASK candles. Index is UTC candle OPEN."""
    missing = set(RAW_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"Missing source columns: {sorted(missing)}")
    frame = raw.copy()
    numeric_ts = pd.to_numeric(frame["ts"], errors="raise")
    # Source timestamps are UNIX seconds, not milliseconds.
    frame["ts"] = pd.to_datetime(numeric_ts, unit="s", utc=True, errors="raise")
    for column in PRICE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame = frame.sort_values("ts")
    if frame["ts"].duplicated().any():
        raise ValueError("Duplicate candle timestamps: quarantine the source")
    frame = frame.set_index("ts")
    if strict:
        if frame.index.hasnans:
            raise ValueError("Invalid UTC candle timestamp: quarantine the source")
        price_array = frame[list(PRICE_COLUMNS)].to_numpy(dtype=float)
        invalid = (
            pd.Series(~np.isfinite(price_array).all(axis=1), index=frame.index)
            | (frame[list(PRICE_COLUMNS)] <= 0).any(axis=1)
            | (frame.index.asi8 % 60_000_000_000 != 0)
            | (frame["h"] < frame[["o", "c", "l"]].max(axis=1))
            | (frame["l"] > frame[["o", "c", "h"]].min(axis=1))
            | (frame["ah"] < frame[["ao", "ac", "al"]].max(axis=1))
            | (frame["al"] > frame[["ao", "ac", "ah"]].min(axis=1))
            | (frame["ao"] < frame["o"])
            | (frame["ac"] < frame["c"])
            | (frame["ah"] < frame["h"])
            | (frame["al"] < frame["l"])
        )
        if invalid.any():
            raise ValueError(f"{int(invalid.sum())} anomalous BID/ASK candles: quarantine before running")
    return frame


def quality(frame: pd.DataFrame) -> dict:
    """Report observations without assuming every missing minute is bad data."""
    if frame.empty:
        return {"rows": 0, "status": "empty"}
    deltas = frame.index.to_series().diff().dt.total_seconds().dropna()
    missing = (deltas / 60 - 1).clip(lower=0)
    bid_bad = (frame["h"] < frame[["o", "c", "l"]].max(axis=1)) | (
        frame["l"] > frame[["o", "c", "h"]].min(axis=1)
    )
    ask_bad = (frame["ah"] < frame[["ao", "ac", "al"]].max(axis=1)) | (
        frame["al"] > frame[["ao", "ac", "ah"]].min(axis=1)
    )
    price_array = frame[list(PRICE_COLUMNS)].to_numpy(dtype=float)
    nonfinite_rows = ~np.isfinite(price_array).all(axis=1)
    nonpositive_rows = (price_array <= 0).any(axis=1)
    return {
        "rows": int(len(frame)),
        "start_utc": frame.index.min().isoformat(),
        "end_utc": frame.index.max().isoformat(),
        "duplicate_timestamps": int(frame.index.duplicated().sum()),
        "non_60s_intervals": int((deltas != 60).sum()),
        "gaps_over_10min": int((deltas > 600).sum()),
        "missing_observed_minutes": int(missing.sum()),
        "bid_ohlc_anomalies": int(bid_bad.sum()),
        "ask_ohlc_anomalies": int(ask_bad.sum()),
        "ask_below_bid_open": int((frame["ao"] < frame["o"]).sum()),
        "ask_below_bid_close": int((frame["ac"] < frame["c"]).sum()),
        "ask_below_bid_high": int((frame["ah"] < frame["h"]).sum()),
        "ask_below_bid_low": int((frame["al"] < frame["l"]).sum()),
        "nonfinite_price_rows": int(nonfinite_rows.sum()),
        "nonpositive_price_rows": int(nonpositive_rows.sum()),
        "note": "Gaps include legitimate market closures; this is NOT proof of corrupt data.",
    }


def fingerprint_loaded_m1(frame: pd.DataFrame) -> str:
    """Deterministic SHA-256 of the EXACT observed Bid/Ask bars in this run.

    Hashes UTC nanosecond timestamps plus all 8 price columns, not just the
    name of a source ZIP or a mutable Parquet manifest. The stable little-
    endian float64 encoding is versioned to expose incompatible model changes.
    This does not authenticate the original data provider or broker fills.
    """
    required = list(PRICE_COLUMNS)
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("Expected nonempty M1 time series")
    if frame.index.tz is None or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("M1 index must be timezone-aware, sorted and unique")
    if (frame.index.asi8 % 60_000_000_000 != 0).any():
        raise ValueError("M1 timestamps must align exactly to minute opens")
    if not set(required).issubset(frame.columns):
        raise ValueError("Missing original Bid/Ask price columns")
    prices = frame[required].to_numpy(dtype="<f8", copy=True)
    if not np.isfinite(prices).all():
        raise ValueError("Missing or invalid prices")
    digest = hashlib.sha256()
    digest.update(b"NRF-XAUUSD-M1-BIDASK-SLICE-V1\x00")
    digest.update(",".join(required).encode("ascii"))
    digest.update(b"\x00")
    digest.update(frame.index.asi8.astype("<i8", copy=False).tobytes(order="C"))
    digest.update(prices.tobytes(order="C"))
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _records_from_bytes(content: bytes) -> pd.DataFrame:
    obj = json.loads(content)
    if isinstance(obj, dict):
        obj = obj.get("data", obj.get("candles"))
    if not isinstance(obj, list):
        raise ValueError("JSON must be a candle array or have a data/candles array")
    return pd.DataFrame.from_records(obj)


def read_source(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".json":
        frame = _records_from_bytes(path.read_bytes())
    elif path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    elif path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
        if isinstance(frame.index, pd.DatetimeIndex):
            # read_source() is also a public ingestion entry point. Do not
            # allow direct Parquet callers to bypass the load_market() gate.
            return validate_loaded_m1(frame)
    else:
        raise ValueError("Expected .json, .csv, or .parquet")
    return normalize(frame)


def import_gold_zip(source: str | Path, destination: str | Path) -> dict:
    """Ingest one annual JSON at a time; never commit raw market data to Git."""
    source, destination = Path(source), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / "manifest.json").exists() or any(destination.glob("xauusd_*.parquet")):
        raise FileExistsError("Destination already contains imported data; use a new versioned directory")
    entries = []
    seen_years: set[int] = set()
    with zipfile.ZipFile(source) as archive:
        for name in sorted(n for n in archive.namelist() if n.lower().endswith(".json")):
            match = re.search(r"(20\d{2})", Path(name).name)
            if not match:
                raise ValueError(f"Cannot identify year for {name}")
            year = int(match.group(1))
            if year in seen_years:
                raise ValueError(f"Multiple source JSON members for year {year}; refusing overwrite")
            seen_years.add(year)
            member_bytes = archive.read(name)
            records = _records_from_bytes(member_bytes)
            # Quality scan is retained even if ingest refuses invalid candles.
            # Do NOT quietly remove or interpolate anomalies.
            frame = normalize(records, strict=False)
            checks = quality(frame)
            anomalies = (
                checks["bid_ohlc_anomalies"]
                + checks["ask_ohlc_anomalies"]
                + checks["ask_below_bid_open"]
                + checks["ask_below_bid_close"]
                + checks["ask_below_bid_high"]
                + checks["ask_below_bid_low"]
                + checks["nonfinite_price_rows"]
                + checks["nonpositive_price_rows"]
            )
            wrong_year = int((frame.index.year != year).sum())
            off_minute = int(((frame.index.asi8 // 1_000_000_000) % 60 != 0).sum())
            accepted = anomalies == 0 and wrong_year == 0 and off_minute == 0
            row = {
                "year": year, "source_member": name,
                "source_member_sha256": hashlib.sha256(member_bytes).hexdigest(),
                **checks,
                "wrong_year_rows": wrong_year,
                "off_minute_timestamps": off_minute,
                "accepted": accepted,
            }
            entries.append(row)
            if not accepted:
                continue
            frame.to_parquet(destination / f"xauusd_{year}.parquet", compression="zstd")
    manifest = {
        "format_version": 1,
        "instrument": "XAUUSD",
        "source_sha256": sha256_file(source),
        "timezone": "UTC",
        "candle_timestamp": "open",
        "cost_model": "all_in_fixed_fee_not_actual_broker_execution",
        "annual_partitions": entries,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest



def validate_loaded_m1(frame: pd.DataFrame) -> pd.DataFrame:
    """Fail closed on source or Parquet M1 quotes before any backtest.

    This is deliberately checked after slicing as well as on JSON import:
    a cached Parquet partition can be modified after its original manifest
    was written. No missing minutes are fabricated or filled.
    """
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("Loaded M1 requires a nonempty UTC DatetimeIndex")
    idx = frame.index
    if (idx.tz is None or str(idx.tz) != "UTC" or idx.hasnans or
            idx.has_duplicates or not idx.is_monotonic_increasing or
            (idx.asi8 % 60_000_000_000 != 0).any()):
        raise ValueError("Loaded M1 requires unique sorted UTC minute opens")
    missing = set(PRICE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Loaded M1 missing BID/ASK columns: {sorted(missing)}")
    prices = frame[list(PRICE_COLUMNS)].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("Loaded M1 contains nonfinite or nonpositive BID/ASK")
    bid, ask = prices[:, :4], prices[:, 4:]
    for side in (bid, ask):
        opn, high, low, close = side.T
        if ((high < np.maximum.reduce((opn, low, close))) |
                (low > np.minimum.reduce((opn, high, close)))).any():
            raise ValueError("Loaded M1 contains invalid BID/ASK OHLC")
    if (ask < bid).any():
        raise ValueError("Loaded M1 contains crossed BID/ASK OHLC")
    return frame


def load_market(path: str | Path, start: str, end: str) -> pd.DataFrame:
    """End is inclusive UTC. Prefer an imported Parquet directory."""
    path = Path(path)
    begin = pd.Timestamp(start, tz="UTC")
    finish = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    if path.suffix.lower() == ".zip":
        parts = []
        with zipfile.ZipFile(path) as archive:
            selected_members = {}
            for member in archive.namelist():
                if not member.lower().endswith(".json"):
                    continue
                match = re.search(r"(20\d{2})", Path(member).name)
                if not match:
                    continue
                year = int(match.group(1))
                if begin.year <= year <= finish.year:
                    if year in selected_members:
                        raise ValueError(f"Duplicate year {year} within ZIP")
                    selected_members[year] = member
            for year in range(begin.year, finish.year + 1):
                if year in selected_members:
                    part = normalize(_records_from_bytes(archive.read(selected_members[year])))
                    if (part.index.year != year).any():
                        raise ValueError(f"ZIP member for {year} contains another year")
                    parts.append(part)
        if not parts:
            raise ValueError("No source years found in the requested ZIP date range")
        frame = pd.concat(parts).sort_index()
    elif path.is_dir():
        parts = []
        for year in range(begin.year, finish.year + 1):
            candidate = path / f"xauusd_{year}.parquet"
            if candidate.is_file():
                parts.append(pd.read_parquet(candidate))
        if not parts:
            raise ValueError("No year partitions for requested range; import data first")
        frame = pd.concat(parts).sort_index()
    else:
        frame = read_source(path)
    selected = frame.loc[(frame.index >= begin) & (frame.index < finish)].copy()
    if selected.empty:
        raise ValueError("No data in requested period")
    return validate_loaded_m1(selected)
