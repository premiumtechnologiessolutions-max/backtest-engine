import pandas as pd
import pytest

from norisk_quant.ticks import (
    TickSource, audit_tick_csv, compare_tick_bid_to_m1,
    ensure_tick_capability, normalize_ticks,
)


def sample():
    return pd.DataFrame(
        {
            "ts_utc": [
                "2024-05-01T00:00:00.000Z",
                "2024-05-01T00:00:05.000Z",
                "2024-05-01T00:00:30.000Z",
            ],
            "bid": [100.0, 101.0, 100.5],
            "ask": [100.4, 101.4, 100.9],
        }
    )


def source():
    return TickSource(provider="example broker (unverified)", symbol="XAUUSD")


def test_real_tick_source_has_bid_ask_and_utc():
    ticks = normalize_ticks(sample(), source())
    assert str(ticks.index.tz) == "UTC"
    assert len(ticks) == 3
    assert ticks.attrs["quote_provenance_declared_not_verified"] is True


def test_naive_timestamp_and_inverted_quote_rejected():
    frame = sample()
    frame.loc[0, "ts_utc"] = "2024-05-01T00:00:00"
    with pytest.raises(ValueError, match="UTC offset"):
        normalize_ticks(frame, source())
    frame = sample()
    frame.loc[1, "ask"] = 100.0
    with pytest.raises(ValueError, match="Invalid bid/ask"):
        normalize_ticks(frame, source())


def test_same_timestamp_requires_explicit_sequence():
    frame = sample()
    frame.loc[1, "ts_utc"] = frame.loc[0, "ts_utc"]
    with pytest.raises(ValueError, match="sequence"):
        normalize_ticks(frame, source())
    frame["seq"] = [1, 2, 1]
    ticks = normalize_ticks(frame, source())
    assert len(ticks) == 3


def test_synthetic_ticks_never_pass_real_tick_gate():
    synthetic = TickSource("OHLC converter", "XAUUSD", source_kind="synthetic")
    with pytest.raises(ValueError, match="Synthetic"):
        normalize_ticks(sample(), synthetic)
    with pytest.raises(ValueError, match="Synthetic"):
        ensure_tick_capability(
            tick_audit={"rows": 3, "source_file_sha256": "abc", "source_kind_declared": "synthetic"},
            claimed_mode="observed_tick_research",
        )
    with pytest.raises(ValueError, match="requires"):
        ensure_tick_capability(tick_audit=None, claimed_mode="observed_tick_research")


def test_tick_bid_to_m1_comparison_reports_missing_without_fabrication():
    ticks = normalize_ticks(sample(), source())
    idx = pd.to_datetime(
        ["2024-05-01T00:00:00Z", "2024-05-01T00:01:00Z"], utc=True
    )
    bars = pd.DataFrame(
        {
            "o": [100.0, 102.0],
            "h": [101.0, 102.0],
            "l": [100.0, 102.0],
            "c": [100.5, 102.0],
        }, index=idx
    )
    result = compare_tick_bid_to_m1(ticks, bars)
    assert bool(result.iloc[0]["tick_present"])
    assert not bool(result.iloc[0]["mismatch"])
    assert not bool(result.iloc[1]["tick_present"])


def test_tick_csv_audit_is_sha_bound_and_not_authenticated(tmp_path):
    path = tmp_path / "observed.csv"
    sample().to_csv(path, index=False)
    manifest = audit_tick_csv(path, source())
    assert manifest["rows"] == 3
    assert len(manifest["source_file_sha256"]) == 64
    assert manifest["source_authentication"] == "NOT_VERIFIED"
    ensure_tick_capability(tick_audit=manifest, claimed_mode="observed_tick_research")


def test_tick_comparison_fails_closed_on_nonfinite_tolerance():
    ticks = normalize_ticks(sample(), source())
    bars = pd.DataFrame(
        {"o": [100.0], "h": [101.0], "l": [100.0], "c": [100.5]},
        index=pd.to_datetime(["2024-05-01T00:00:00Z"], utc=True),
    )
    for invalid in (float("nan"), float("inf"), -1.0, True, "0.1"):
        with pytest.raises(ValueError, match="finite and nonnegative"):
            compare_tick_bid_to_m1(ticks, bars, tolerance=invalid)
    valid = compare_tick_bid_to_m1(ticks, bars, tolerance=0.0)
    assert bool(valid.iloc[0]["tick_present"])
    assert not bool(valid.iloc[0]["mismatch"])


def test_tick_comparison_rejects_corrupt_ohlc_and_timestamps():
    ticks = normalize_ticks(sample(), source())
    bars = pd.DataFrame(
        {"o": [100.0], "h": [101.0], "l": [100.0], "c": [100.5]},
        index=pd.to_datetime(["2024-05-01T00:00:00Z"], utc=True),
    )
    for field, invalid in (("h", float("nan")), ("h", float("inf")),
                           ("h", 99.0), ("l", 102.0)):
        bad = bars.copy()
        bad.loc[bad.index[0], field] = invalid
        with pytest.raises(ValueError, match="Invalid BID M1 OHLC"):
            compare_tick_bid_to_m1(ticks, bad)
    duplicated = pd.concat([bars, bars])
    with pytest.raises(ValueError, match="unique sorted minute opens"):
        compare_tick_bid_to_m1(ticks, duplicated)
    off_minute = bars.copy()
    off_minute.index = off_minute.index + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="unique sorted minute opens"):
        compare_tick_bid_to_m1(ticks, off_minute)
    bad_ticks = ticks.copy()
    bad_ticks.loc[bad_ticks.index[0], "bid"] = float("nan")
    with pytest.raises(ValueError, match="Invalid tick BID quotes"):
        compare_tick_bid_to_m1(bad_ticks, bars)
