"""FAC024 prospective manifest: synthetic only, no private market data."""
from copy import deepcopy
import hashlib
import pandas as pd
import pytest
from norisk_quant.prospective_manifest import (
    EXPECTED_MONTHS, all_months_registered, append_record, empty_manifest,
    register_closed_month, verify_manifest, verify_partition_file,
)


def source(tmp_path, month="2026-11"):
    idx = pd.date_range(month + "-02T00:00:00Z", periods=3, freq="min")
    frame = pd.DataFrame({k: [100., 100., 100.] for k in ("o", "h", "l", "c")}, index=idx)
    for k in ("ao", "ah", "al", "ac"):
        frame[k] = 100.4
    path = tmp_path / "SYNTHETIC_NOT_REAL_GOLD.dat"
    path.write_bytes(b"SYNTHETIC_ONLY_NOT_GOLD")
    return path, frame


def record(tmp_path, month="2026-11"):
    p, frame = source(tmp_path, month)
    next_month = pd.Timestamp(month + "-01", tz="UTC") + pd.offsets.MonthBegin(1)
    return register_closed_month(month, p, frame, registered_at_utc=next_month,
                                 as_of_utc=next_month + pd.Timedelta(days=1))


def test_exactly_twelve_frozen_months():
    assert len(EXPECTED_MONTHS) == 12
    assert (EXPECTED_MONTHS[0], EXPECTED_MONTHS[-1]) == ("2026-11", "2027-10")


def test_registration_hash_and_mutation(tmp_path):
    p, _ = source(tmp_path)
    r = record(tmp_path)
    assert r["source_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert r["observed_m1_rows"] == 3
    assert verify_partition_file(r, p)
    p.write_bytes(p.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="changed"):
        verify_partition_file(r, p)


def test_append_chain_and_tamper(tmp_path):
    m = append_record(empty_manifest(), record(tmp_path))
    assert verify_manifest(m) and not all_months_registered(m)
    tampered = deepcopy(m)
    tampered["records"][0]["record"]["source_bytes"] += 1
    with pytest.raises(ValueError, match="digest"):
        verify_manifest(tampered)


def test_duplicate_rejected(tmp_path):
    r = record(tmp_path)
    with pytest.raises(ValueError, match="order"):
        append_record(append_record(empty_manifest(), r), r)


def test_skip_month_rejected(tmp_path):
    with pytest.raises(ValueError, match="order"):
        append_record(empty_manifest(), record(tmp_path, "2026-12"))


def test_before_month_end_rejected(tmp_path):
    p, f = source(tmp_path)
    with pytest.raises(ValueError, match="finish"):
        register_closed_month("2026-11", p, f, registered_at_utc="2026-11-30T23:59:00Z",
                              as_of_utc="2026-12-01T00:00:00Z")


def test_asof_before_registration_rejected(tmp_path):
    p, f = source(tmp_path)
    with pytest.raises(ValueError, match="finish"):
        register_closed_month("2026-11", p, f, registered_at_utc="2026-12-02T00:00:00Z",
                              as_of_utc="2026-12-01T00:00:00Z")


def test_non_utc_registration_rejected(tmp_path):
    p, f = source(tmp_path)
    with pytest.raises(ValueError, match="UTC"):
        register_closed_month("2026-11", p, f, registered_at_utc="2026-12-01T01:00:00+01:00",
                              as_of_utc="2026-12-02T00:00:00Z")


def test_naive_observed_index_rejected(tmp_path):
    p, f = source(tmp_path)
    f.index = f.index.tz_localize(None)
    with pytest.raises(ValueError, match="UTC"):
        register_closed_month("2026-11", p, f, registered_at_utc="2026-12-01T00:00:00Z",
                              as_of_utc="2026-12-02T00:00:00Z")


def test_missing_minutes_are_not_fabricated(tmp_path):
    p, f = source(tmp_path)
    f = f.drop(f.index[1])
    r = register_closed_month("2026-11", p, f, registered_at_utc="2026-12-01T00:00:00Z",
                              as_of_utc="2026-12-02T00:00:00Z")
    assert r["observed_m1_rows"] == 2


def test_duplicate_minutes_rejected(tmp_path):
    p, f = source(tmp_path)
    f.index = pd.DatetimeIndex([f.index[0], f.index[0], f.index[2]])
    with pytest.raises(ValueError, match="unique"):
        register_closed_month("2026-11", p, f, registered_at_utc="2026-12-01T00:00:00Z",
                              as_of_utc="2026-12-02T00:00:00Z")


def test_outside_month_rejected(tmp_path):
    p, f = source(tmp_path)
    f.index = f.index + pd.Timedelta(days=40)
    with pytest.raises(ValueError, match="inside month"):
        register_closed_month("2026-11", p, f, registered_at_utc="2026-12-01T00:00:00Z",
                              as_of_utc="2026-12-02T00:00:00Z")


def test_crossed_quotes_rejected(tmp_path):
    p, f = source(tmp_path)
    f.iloc[0, f.columns.get_loc("ao")] = 99.
    with pytest.raises(ValueError, match="Crossed"):
        register_closed_month("2026-11", p, f, registered_at_utc="2026-12-01T00:00:00Z",
                              as_of_utc="2026-12-02T00:00:00Z")


def test_text_quotes_rejected(tmp_path):
    p, f = source(tmp_path)
    f["ao"] = ["100.4"] * len(f)
    with pytest.raises(ValueError, match="numeric"):
        register_closed_month("2026-11", p, f, registered_at_utc="2026-12-01T00:00:00Z",
                              as_of_utc="2026-12-02T00:00:00Z")


def test_empty_source_rejected(tmp_path):
    p, f = source(tmp_path)
    p.write_bytes(b"")
    with pytest.raises(ValueError, match="Empty"):
        register_closed_month("2026-11", p, f, registered_at_utc="2026-12-01T00:00:00Z",
                              as_of_utc="2026-12-02T00:00:00Z")


def test_broken_chain_rejected(tmp_path):
    m = append_record(empty_manifest(), record(tmp_path))
    m["records"][0]["previous_digest"] = "a" * 64
    with pytest.raises(ValueError, match="broken"):
        verify_manifest(m)


def test_boolean_row_count_rejected(tmp_path):
    r = record(tmp_path)
    r["observed_m1_rows"] = True
    with pytest.raises(ValueError, match="integer"):
        append_record(empty_manifest(), r)


def test_bad_sha_rejected(tmp_path):
    r = record(tmp_path)
    r["source_sha256"] = "G" * 64
    with pytest.raises(ValueError, match="SHA256"):
        append_record(empty_manifest(), r)


@pytest.mark.parametrize(("column", "bad_value"), [
    ("h", 99.0), ("l", 101.0), ("ah", 99.9), ("al", 101.0),
])
def test_impossible_bid_ask_bar_geometry_rejected(tmp_path, column, bad_value):
    p, f = source(tmp_path)
    f.loc[f.index[0], column] = bad_value
    with pytest.raises(ValueError, match="bar geometry"):
        register_closed_month("2026-11", p, f,
                              registered_at_utc="2026-12-01T00:00:00Z",
                              as_of_utc="2026-12-02T00:00:00Z")


def test_complex_quotes_rejected_without_dropping_imaginary_component(tmp_path):
    p, f = source(tmp_path)
    f["o"] = [100 + 1j] * len(f)
    with pytest.raises(ValueError, match="real numeric"):
        register_closed_month("2026-11", p, f,
                              registered_at_utc="2026-12-01T00:00:00Z",
                              as_of_utc="2026-12-02T00:00:00Z")


def test_duplicate_quote_column_rejected(tmp_path):
    p, f = source(tmp_path)
    f = pd.concat([f, f[["o"]]], axis=1)
    with pytest.raises(ValueError, match="column names must be unique"):
        register_closed_month("2026-11", p, f,
                              registered_at_utc="2026-12-01T00:00:00Z",
                              as_of_utc="2026-12-02T00:00:00Z")
