"""B07 private month source candidate — no trading and immutable file creation."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import zipfile

import pytest

from norisk_quant.month_source_manifest import build_month_source_candidate
from norisk_quant.source_registry import verify_record_manifest
from scripts.prepare_gold_month_manifest import write_new_private_manifest, main

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def observed_bars(*, first="2012-01-02T23:00:00+00:00",
                  last="2012-01-31T23:59:00+00:00"):
    def row(at, offset):
        return {
            "ts": int(datetime.fromisoformat(at).timestamp()),
            "o": 2000.0+offset, "h": 2002.0+offset,
            "l": 1999.0+offset, "c": 2001.0+offset,
            "ao": 2000.2+offset, "ah": 2002.2+offset,
            "al": 1999.2+offset, "ac": 2001.2+offset,
        }
    return [row(first, 0), row(last, 0.5)]


def sample_zip(tmp_path, *, records=None, member="2012.json"):
    zip_path = tmp_path / "Gold_original_private.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, json.dumps(observed_bars() if records is None else records))
    return zip_path


def private_dir(tmp_path):
    dst = tmp_path / "private_manifest_storage"
    dst.mkdir()
    if os.name == "posix":
        dst.chmod(0o700)
    return dst


def test_real_calendar_closed_first_day_preserves_true_m1_row_count(tmp_path):
    archive = sample_zip(tmp_path)
    cand = build_month_source_candidate(archive, 2012, 1, observed_now=NOW)
    assert cand.rows == 2
    assert cand.first_unobserved_minutes == 47*60
    assert cand.last_unobserved_minutes == 0
    row = verify_record_manifest(cand.manifest)
    assert row.rows == 2
    assert row.family == "original_gold_m1_bidask"
    assert row.source_claim == "ORIGINAL_M1_DECLARED"
    assert row.source_authentication == "NOT_VERIFIED"
    report = cand.public_status()
    assert report["status"] == "LOCAL_SOURCE_CANDIDATE_NOT_PREREGISTERED"
    assert report["execution"] == "NONE"
    assert report["profitability_verified"] is False
    assert report["independent_oos"] is False
    assert report["market_closure_classification"] == "NOT_AUDITED"


def test_manifest_is_repeatable_from_identical_original_source(tmp_path):
    archive = sample_zip(tmp_path)
    first = build_month_source_candidate(archive, 2012, 1, observed_now=NOW)
    second = build_month_source_candidate(archive, 2012, 1, observed_now=NOW)
    assert first.manifest == second.manifest
    assert first.public_status() == second.public_status()


def test_source_single_ask_quote_change_invalidates_digest(tmp_path):
    archive = sample_zip(tmp_path)
    before = build_month_source_candidate(archive, 2012, 1, observed_now=NOW)
    new = observed_bars()
    new[1]["ac"] += 0.01
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as a:
        a.writestr("2012.json", json.dumps(new))
    after = build_month_source_candidate(archive, 2012, 1, observed_now=NOW)
    assert before.manifest["id"] != after.manifest["id"]
    assert before.manifest["record"]["source_file_sha256"] != after.manifest["record"]["source_file_sha256"]


def test_one_annual_member_per_year_only(tmp_path):
    archive = sample_zip(tmp_path)
    with zipfile.ZipFile(archive, "a") as a:
        a.writestr("copy_2012.json", json.dumps(observed_bars()))
    with pytest.raises(ValueError, match="one bounded"):
        build_month_source_candidate(archive, 2012, 1, observed_now=NOW)


def test_missing_annual_member_is_rejected(tmp_path):
    archive = sample_zip(tmp_path, member="2013.json")
    with pytest.raises(ValueError, match="one bounded"):
        build_month_source_candidate(archive, 2012, 1, observed_now=NOW)


def test_edge_of_market_month_cannot_exceed_72_hours(tmp_path):
    archive = sample_zip(
        tmp_path, records=observed_bars(first="2012-01-05T00:00:00+00:00"))
    with pytest.raises(ValueError, match="72-hour"):
        build_month_source_candidate(archive, 2012, 1, observed_now=NOW)


def test_incomplete_trailing_month_is_rejected(tmp_path):
    archive = sample_zip(
        tmp_path, records=observed_bars(last="2012-01-20T12:00:00+00:00"))
    with pytest.raises(ValueError, match="72-hour"):
        build_month_source_candidate(archive, 2012, 1, observed_now=NOW)


@pytest.mark.parametrize("year,month", [(2026,10),(2027,1),(2012,13),(2012,0),(2009,12)])
def test_future_open_or_unsupported_months_fail_closed(tmp_path, year, month):
    archive = sample_zip(tmp_path)
    with pytest.raises(ValueError):
        build_month_source_candidate(archive, year, month, observed_now=NOW)


def test_bad_original_source_file_rejected(tmp_path):
    src = tmp_path / "broken.zip"
    src.write_bytes(b"pretend broker source")
    with pytest.raises(ValueError, match="decompressed"):
        build_month_source_candidate(src, 2012, 1, observed_now=NOW)


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only private manifest persistence")
def test_cli_prepares_owner_only_candidate_once_without_mutation(tmp_path, capsys):
    archive = sample_zip(tmp_path)
    directory = private_dir(tmp_path)
    path = directory / "2012-01-source-manifest.json"
    argv = ["--source",str(archive),"--year","2012","--month","1","--out",str(path)]
    assert main(argv) == 0
    displayed = json.loads(capsys.readouterr().out)
    assert displayed["status"] == "LOCAL_SOURCE_CANDIDATE_NOT_PREREGISTERED"
    assert displayed["year"] == 2012
    assert displayed["month"] == 1
    assert displayed["rows"] == 2
    assert "2000." not in str(displayed)
    assert str(archive) not in str(displayed)
    assert path.stat().st_mode & 0o077 == 0
    assert verify_record_manifest(json.loads(path.read_text())) is not None
    before = path.read_bytes()
    with pytest.raises(SystemExit) as e:
        main(argv)
    assert e.value.code == 2
    assert path.read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only private manifest persistence")
def test_reject_publicly_readable_destination_directory(tmp_path):
    dst = tmp_path / "public"
    dst.mkdir()
    dst.chmod(0o755)
    with pytest.raises(ValueError, match="owner-only"):
        write_new_private_manifest(dst/"sensitive.json", {"hello":"world"})


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only private manifest persistence")
def test_exclusive_create_race_cannot_delete_another_process_file(tmp_path, monkeypatch):
    from scripts import prepare_gold_month_manifest as cli
    target = private_dir(tmp_path) / "owner.json"
    real_open = cli.os.open

    def winner(path, *args, **kwargs):
        with open(path, "w", encoding="utf-8") as out:
            out.write("concurrent owner's record")
        raise FileExistsError("created elsewhere")

    monkeypatch.setattr(cli.os, "open", winner)
    with pytest.raises(FileExistsError):
        cli.write_new_private_manifest(target, {"a":1})
    assert target.read_text(encoding="utf-8") == "concurrent owner's record"
    monkeypatch.setattr(cli.os, "open", real_open)


def test_source_candidate_is_never_strategy_or_trading_evidence(tmp_path):
    archive = sample_zip(tmp_path)
    result = build_month_source_candidate(archive, 2012, 1, observed_now=NOW)
    public = result.public_status()
    assert public["source_authentication"] == "NOT_VERIFIED"
    assert public["data_rights"] == "UNVERIFIED"
    for field in ("net_profit","live_order","profitable_month","risk_approved","strategy_id"):
        assert field not in str(public)
    assert "source_file_sha256" not in public
    assert "observed_quote_sha256" not in public


def test_prepared_manifest_matches_existing_worker_read_only_source_gate(tmp_path, monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    from norisk_quant.research_control_plane import (
        SCHEMA, EXTERNAL_SOURCE, proposal_identity,
    )
    source = sample_zip(tmp_path)
    manifest = build_month_source_candidate(source, 2012, 1, observed_now=NOW)
    p = {
        "schema": SCHEMA, "producer": EXTERNAL_SOURCE, "agent": "nova",
        "campaign_id": "b07_source_only", "asset": "XAUUSD",
        "dataset_sha256": manifest.manifest["record"]["source_file_sha256"],
        "engine_commit": "b"*40, "strategy_id": "m1-sweep",
        "parameters": {
            "sweep_lookback": 20, "sweep_min_excess_usd": 0.15,
            "sweep_reclaim_usd": 0.10, "sweep_stop_buffer_usd": 0.25,
            "sweep_reward_risk": 2.0, "sweep_max_stop_usd": 20.0,
        },
        "timeframe": "M1", "window_start_utc": "2012-01-01T00:00:00Z",
        "window_end_exclusive_utc": "2012-02-01T00:00:00Z",
        "quantity_ounces": 1.0, "fee_all_in_per_ounce": 0.40,
        "execution_mode": "m1_conservative",
        "exposure_context": "historical_exposed",
    }
    job_id, body, _ = proposal_identity(p)
    monkeypatch.setattr(worker,"inspect_local_checkout",lambda _: "b"*40)
    proof = worker.preflight_queued_research(
        json.loads(body), source_manifest=manifest.manifest,
        data_zip=source, checkout=tmp_path)
    assert proof["experiment_id"] == job_id
    assert proof["source_manifest_id"] == manifest.manifest["id"]
    assert proof["execution"] == "NONE_PREFLIGHT_ONLY"
    assert proof["profitability_verified"] is False
    assert proof["independent_oos"] is False
    assert proof["plan"]["jobs"][0]["strategy"] == "m1-sweep"
    assert proof["plan"]["jobs"][0]["start"] == "2012-01-01"
    assert proof["plan"]["jobs"][0]["end"] == "2012-01-31"


def test_worker_rejects_prepared_manifest_when_original_archive_changes(tmp_path, monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    from norisk_quant.research_control_plane import SCHEMA, EXTERNAL_SOURCE, proposal_identity
    src = sample_zip(tmp_path)
    cand = build_month_source_candidate(src, 2012, 1, observed_now=NOW)
    p = {
        "schema":SCHEMA, "producer":EXTERNAL_SOURCE, "agent":"nova",
        "campaign_id":"b07_data_mutation", "asset":"XAUUSD",
        "dataset_sha256":cand.manifest["record"]["source_file_sha256"],
        "engine_commit":"b"*40, "strategy_id":"m1-sweep",
        "parameters":{"sweep_lookback":20}, "timeframe":"M1",
        "window_start_utc":"2012-01-01T00:00:00Z",
        "window_end_exclusive_utc":"2012-02-01T00:00:00Z",
        "quantity_ounces":1.0, "fee_all_in_per_ounce":0.40,
        "execution_mode":"m1_conservative", "exposure_context":"historical_exposed",
    }
    _, body, _=proposal_identity(p)
    monkeypatch.setattr(worker,"inspect_local_checkout",lambda _: "b"*40)
    src.write_bytes(src.read_bytes() + b"X")
    with pytest.raises((ValueError, zipfile.BadZipFile), match="bytes differ|Damaged|Original Gold"):
        worker.preflight_queued_research(
            json.loads(body), source_manifest=cand.manifest,
            data_zip=src,checkout=tmp_path,
        )
