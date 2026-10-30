"""Synthetic-only M1 risk evidence tests; never load original Gold data."""
import csv
import hashlib
import json
import pytest
from scripts import research_equity_m1_audit as audit

SOURCE = hashlib.sha256(b"synthetic archive").hexdigest()
ENGINE = "a" * 40


def fixture(tmp_path):
    archive = tmp_path / "private.zip"
    archive.write_bytes(b"synthetic archive")
    run = tmp_path / "run"
    run.mkdir()
    summary = {
        "execution": "synthetic_same_reference_bid_ohlc_fixed_all_in_fee",
        "source_fingerprints": {"source_file_sha256": SOURCE, "git_revision_env": ENGINE},
        "settings": {"roundtrip_cost_per_ounce": 0.4},
        "months_observed": 2, "max_drawdown_observed_m1": 3,
        "last_observed_equity": 1, "last_observed_realized_pnl": 2,
        "start_utc": "2024-01-31T23:56:00+00:00",
        "end_utc": "2024-02-01T00:01:00+00:00",
    }
    (run / "summary.json").write_text(json.dumps(summary))
    with (run / "monthly.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["period", "observed_m1_samples", "month_end_equity", "month_end_drawdown"])
        writer.writerow(["2024-01", 3, -1, 1])
        writer.writerow(["2024-02", 2, 1, 0])
    with (run / "equity_m1.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["at", "realized_pnl", "floating_pnl", "equity", "drawdown"])
        writer.writerows([
            ["2024-01-31 23:56:00+00:00", 0, 2, 2, 0],
            ["2024-01-31 23:57:00+00:00", 0, 0, 0, 2],
            ["2024-01-31 23:59:00+00:00", 0, -1, -1, 3],
            ["2024-02-01 00:00:00+00:00", 2, -1, 1, 1],
            ["2024-02-01 00:01:00+00:00", 2, -1, 1, 1],
        ])
    hashes = {name: audit._hash(run / name) for name in
              ("summary.json", "monthly.csv", "equity_m1.csv")}
    return run, archive, hashes


def test_observed_global_peak_monthly_dd_and_no_fabricated_gap(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    result = audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)
    assert result["observed_m1_samples"] == 5
    assert result["max_observed_m1_global_peak_drawdown_usd_per_oz"] == 3
    assert [m["max_observed_m1_global_peak_drawdown_usd_per_oz"] for m in result["monthly"]] == [3, 1]
    assert [m["observed_gap_events_from_prior_mark"] for m in result["monthly"]] == [1, 0]
    assert result["missing_minutes_filled"] == 0
    assert result["shared_capacity_verified"] is False
    assert result["clean_prospective_oos"] is False


def test_hash_tamper_rejected(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    (run / "equity_m1.csv").write_text("forged")
    with pytest.raises(ValueError, match="SHA mismatch"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_source_archive_mismatch_rejected(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    archive.write_bytes(b"other archive")
    with pytest.raises(ValueError, match="archive SHA"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_wrong_fee_rejected_even_when_hashes_match(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    summary = json.loads((run / "summary.json").read_text())
    summary["settings"]["roundtrip_cost_per_ounce"] = 0.39
    (run / "summary.json").write_text(json.dumps(summary))
    hashes["summary.json"] = audit._hash(run / "summary.json")
    with pytest.raises(ValueError, match="source/code/cost"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_wrong_equity_arithmetic_rejected_even_when_hashes_match(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "equity_m1.csv"
    path.write_text(path.read_text().replace("0,-1,-1,3", "0,-1,1,3"))
    hashes["equity_m1.csv"] = audit._hash(path)
    with pytest.raises(ValueError, match="Realized plus floating"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_wrong_month_sample_count_rejected(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "monthly.csv"
    path.write_text(path.read_text().replace("2024-01,3,", "2024-01,4,"))
    hashes["monthly.csv"] = audit._hash(path)
    with pytest.raises(ValueError, match="samples disagree"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_nonmonotonic_minutes_rejected(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "equity_m1.csv"
    path.write_text(path.read_text().replace("23:57:00", "23:56:00"))
    hashes["equity_m1.csv"] = audit._hash(path)
    with pytest.raises(ValueError, match="Nonmonotonic"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_naive_timestamp_rejected(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "equity_m1.csv"
    path.write_text(path.read_text().replace("23:56:00+00:00", "23:56:00"))
    hashes["equity_m1.csv"] = audit._hash(path)
    with pytest.raises(ValueError, match="exact UTC"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_hardlinked_equity_rejected(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    (tmp_path / "other.csv").hardlink_to(run / "equity_m1.csv")
    with pytest.raises(ValueError, match="hardlinked"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_duplicate_monthly_csv_header_rejected(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "monthly.csv"
    path.write_text(path.read_text().replace("period,observed_m1_samples", "period,period,observed_m1_samples"))
    hashes["monthly.csv"] = audit._hash(path)
    with pytest.raises(ValueError, match="duplicate CSV"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_missing_equity_hash_is_not_verified(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    del hashes["equity_m1.csv"]
    with pytest.raises(ValueError, match="Three independently pinned"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_duplicate_summary_json_key_rejected(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "summary.json"
    path.write_text(path.read_text().replace('"months_observed": 2', '"months_observed": 2, "months_observed": 2'))
    hashes["summary.json"] = audit._hash(path)
    with pytest.raises(ValueError, match="Duplicate JSON"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_wrong_summary_bounds_rejected(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "summary.json"
    summary = json.loads(path.read_text())
    summary["start_utc"] = "2024-01-31T23:55:00+00:00"
    path.write_text(json.dumps(summary))
    hashes["summary.json"] = audit._hash(path)
    with pytest.raises(ValueError, match="first M1 timestamp"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_reversed_monthly_ledger_rejected(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "monthly.csv"
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2], lines[1]]) + "\n")
    hashes["monthly.csv"] = audit._hash(path)
    with pytest.raises(ValueError, match="ordering"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


@pytest.mark.parametrize("fee", [0.4000005, "0.40", True])
def test_exact_canonical_fee_rejects_near_miss_or_non_numeric_type(tmp_path, fee):
    run, archive, hashes = fixture(tmp_path)
    path = run / "summary.json"
    summary = json.loads(path.read_text())
    summary["settings"]["roundtrip_cost_per_ounce"] = fee
    path.write_text(json.dumps(summary))
    hashes["summary.json"] = audit._hash(path)
    with pytest.raises(ValueError, match="source/code/cost"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


@pytest.mark.parametrize("token", ["1e999", "-1e999", "1e309"])
def test_overflowing_json_exponent_rejected_even_in_unused_nested_field(tmp_path, token):
    run, archive, hashes = fixture(tmp_path)
    path = run / "summary.json"
    original = path.read_text()
    path.write_text(original[:-1] + ', "unused": {"value": ' + token + '}}')
    hashes["summary.json"] = audit._hash(path)
    with pytest.raises(ValueError, match="Nonfinite JSON evidence"):
        audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)


def test_large_but_finite_json_exponent_is_accepted(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "summary.json"
    original = path.read_text()
    path.write_text(original[:-1] + ', "unused": {"value": 1e308}}')
    hashes["summary.json"] = audit._hash(path)
    assert audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)["observed_m1_samples"] == 5


def test_month_local_drawdown_resets_from_prior_observed_close(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    result = audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)
    assert [m["max_observed_m1_global_peak_drawdown_usd_per_oz"]
            for m in result["monthly"]] == [3, 1]
    assert [m["month_local_max_observed_m1_close_drawdown_usd_per_oz"]
            for m in result["monthly"]] == [3, 0]
    assert result["max_observed_m1_month_local_drawdown_usd_per_oz"] == 3


def test_month_local_drawdown_uses_intra_month_observed_peak(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "equity_m1.csv"
    original = path.read_text()
    assert "2024-02-01 00:00:00+00:00,2,-1,1,1" in original
    path.write_text(original.replace(
        "2024-02-01 00:00:00+00:00,2,-1,1,1",
        "2024-02-01 00:00:00+00:00,2,0,2,0"))
    hashes["equity_m1.csv"] = audit._hash(path)
    result = audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)
    assert [m["month_local_max_observed_m1_close_drawdown_usd_per_oz"]
            for m in result["monthly"]] == [3, 1]


def test_month_local_gap_anchors_last_observed_not_fabricated_minute(tmp_path):
    run, archive, hashes = fixture(tmp_path)
    path = run / "equity_m1.csv"
    original = path.read_text()
    assert "2024-02-01 00:00:00+00:00,2,-1,1,1\n" in original
    path.write_text(original.replace("2024-02-01 00:00:00+00:00,2,-1,1,1\n", ""))
    hashes["equity_m1.csv"] = audit._hash(path)
    monthly = run / "monthly.csv"
    text = monthly.read_text()
    assert "2024-02,2,1,0" in text
    monthly.write_text(text.replace("2024-02,2,1,0", "2024-02,1,1,0"))
    hashes["monthly.csv"] = audit._hash(monthly)
    result = audit.audit_equity(run, archive, SOURCE, ENGINE, hashes)
    assert result["observed_m1_samples"] == 4
    assert result["monthly"][1]["observed_gap_events_from_prior_mark"] == 1
    assert result["monthly"][1]["month_local_max_observed_m1_close_drawdown_usd_per_oz"] == 0
    assert result["missing_minutes_filled"] == 0
