"""Synthetic-only FAC024 CSV provenance adapter checks; no real market data."""
from hashlib import sha256

import pytest

import norisk_quant.prospective_csv as csv_adapter
from norisk_quant.prospective_manifest import append_record, empty_manifest, verify_manifest


HEADER = "at,o,h,l,c,ao,ah,al,ac\n"
GOOD = (
    "2026-11-02T00:00:00Z,100,101,99,100,100.4,101.4,99.4,100.4\n"
    "2026-11-02T00:01:00Z,100,101,99,100,100.4,101.4,99.4,100.4\n"
)


def register(tmp_path, text=HEADER + GOOD):
    path = tmp_path / "SYNTHETIC_ONLY.csv"
    path.write_bytes(text.encode("utf-8"))
    return path, csv_adapter.register_closed_month_csv(
        "2026-11", path,
        registered_at_utc="2026-12-01T00:00:00Z",
        as_of_utc="2026-12-02T00:00:00Z",
    )


def test_csv_registration_fingerprints_exact_parsed_bytes(tmp_path):
    path, record = register(tmp_path)
    assert record["source_sha256"] == sha256(path.read_bytes()).hexdigest()
    assert record["source_bytes"] == len(path.read_bytes())
    assert record["observed_m1_rows"] == 2
    assert record["first_open_utc"] == "2026-11-02T00:00:00+00:00"
    assert verify_manifest(append_record(empty_manifest(), record))


@pytest.mark.parametrize(("text", "error"), [
    ("at,o,h,l,c,ao,ah,al,ac,o\n" + GOOD, "header"),
    ("at,o,h,l,c,ao,ah,al,ao\n" + GOOD, "header"),
    ("at,o,h,l,c,ao,ah,al,ac,extra\n" + GOOD, "header"),
    (HEADER + "2026-11-02T00:00:00,100,101,99,100,100.4,101.4,99.4,100.4\n", "UTC M1"),
    (HEADER + "2026-11-02T00:00:01Z,100,101,99,100,100.4,101.4,99.4,100.4\n", "UTC M1"),
    (HEADER + "2026-11-02T00:00:00+00:00,100,101,99,100,100.4,101.4,99.4,100.4\n", "UTC M1"),
    (HEADER + "2026-11-02T00:00:00Z,100,101,99,100,100.4,101.4,99.4\n", "nine fields"),
    (HEADER + "2026-11-02T00:00:00Z,100,101,99,100,100.4,101.4,99.4,100.4,unexpected\n", "nine fields"),
    (HEADER + "2026-11-02T00:00:00Z,100,101,99,100,NaN,101.4,99.4,100.4\n", "decimal"),
    (HEADER + "2026-11-02T00:00:00Z,100,101,99,100,inf,101.4,99.4,100.4\n", "decimal"),
    (HEADER + "2026-11-02T00:00:00Z,100,101,99,100,1e3,101.4,99.4,100.4\n", "decimal"),
    (HEADER + "2026-11-02T00:00:00Z,100,99,99,100,100.4,101.4,99.4,100.4\n", "geometry"),
    (HEADER + "2026-11-02T00:00:00Z,100,101,99,100,99,101.4,99.4,100.4\n", "Crossed"),
    (HEADER + GOOD + GOOD, "unique"),
    (HEADER, "no M1"),
    ("", "Empty"),
])
def test_bad_source_rejected(tmp_path, text, error):
    with pytest.raises(ValueError, match=error):
        register(tmp_path, text)


def test_bad_calendar_month_rejected(tmp_path):
    path = tmp_path / "SYNTHETIC_ONLY.csv"
    path.write_text(HEADER + GOOD, encoding="utf-8")
    with pytest.raises(ValueError, match="inside month"):
        csv_adapter.register_closed_month_csv(
            "2026-12", path, registered_at_utc="2027-01-01T00:00:00Z",
            as_of_utc="2027-01-02T00:00:00Z",
        )


def test_post_parse_file_hash_mismatch_rejected(tmp_path, monkeypatch):
    original = csv_adapter.register_closed_month

    def changed_record(*args, **kwargs):
        result = original(*args, **kwargs)
        result["source_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(csv_adapter, "register_closed_month", changed_record)
    with pytest.raises(ValueError, match="changed between parsing"):
        register(tmp_path)


def test_non_utf8_source_rejected(tmp_path):
    path = tmp_path / "SYNTHETIC_ONLY.csv"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="UTF-8"):
        csv_adapter.register_closed_month_csv(
            "2026-11", path, registered_at_utc="2026-12-01T00:00:00Z",
            as_of_utc="2026-12-02T00:00:00Z",
        )
