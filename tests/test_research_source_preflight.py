"""B05 source-to-AI-experiment integrity: true direct local M1 hashes and UTC."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd
import pytest

from norisk_quant.data import fingerprint_loaded_m1, read_source, sha256_file
from norisk_quant.research_source_loader import preflight_direct_gold_m1_file
from norisk_quant.research_source_preflight import (
    inspect_local_checkout, preflight_gold_m1_source,
)
from norisk_quant.research_control_plane import SCHEMA, EXTERNAL_SOURCE
from norisk_quant.source_registry import (
    register_original_gold_m1, register_terminal_tick_evidence,
)

HEAD = "b" * 40


def data_rows():
    return [
        {"ts": 1704153600, "o": 2000.0, "h": 2001.0, "l": 1999.0,
         "c": 2000.5, "ao": 2000.4, "ah": 2001.4, "al": 1999.4, "ac": 2000.9},
        {"ts": 1704153660, "o": 2000.5, "h": 2002.0, "l": 2000.0,
         "c": 2001.0, "ao": 2000.9, "ah": 2002.4, "al": 2000.4, "ac": 2001.4},
        {"ts": 1704153720, "o": 2001.0, "h": 2003.0, "l": 2000.0,
         "c": 2001.6, "ao": 2001.4, "ah": 2003.4, "al": 2000.4, "ac": 2002.0},
    ]


def fixtures(tmp_path, *, suffix=".json"):
    src = tmp_path / ("original_gold" + suffix)
    if suffix == ".json":
        src.write_text(json.dumps(data_rows()), encoding="utf-8")
    else:
        pd.DataFrame(data_rows()).to_csv(src, index=False)
    loaded = read_source(src)
    manifest = register_original_gold_m1({
        "origin": "user_supplied_gold_m1_bidask",
        "source_file_sha256": sha256_file(src),
        "observed_slice_sha256": fingerprint_loaded_m1(loaded),
        "rows": len(loaded),
        "first_utc": loaded.index[0].isoformat(),
        "last_utc": loaded.index[-1].isoformat(),
    }).internal_manifest()
    proposal = {
        "schema": SCHEMA, "producer": EXTERNAL_SOURCE, "agent": "nova",
        "campaign_id": "campaign_2026_10", "asset": "XAUUSD",
        "dataset_sha256": manifest["record"]["source_file_sha256"],
        "engine_commit": HEAD,
        "strategy_id": "aql_sha256_pinned_gold_candidate",
        "parameters": {"lookback": 20, "threshold": 0.25},
        "timeframe": "M1", "window_start_utc": "2024-01-02T00:00:00Z",
        "window_end_exclusive_utc": "2024-01-02T00:03:00Z",
        "quantity_ounces": 1.0, "fee_all_in_per_ounce": 0.40,
        "execution_mode": "m1_conservative",
        "exposure_context": "historical_exposed",
    }
    return src, loaded, manifest, proposal


def preflight(src, frame, manifest, proposal, **kwargs):
    return preflight_gold_m1_source(
        proposal, manifest, original_source_file=src,
        normalized_m1=frame, observed_engine_commit=kwargs.get("head", HEAD),
    )


def test_original_file_hash_and_all_bidask_quotes_match_record(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    proof = preflight(src, frame, manifest, proposal)
    assert proof.source_manifest_id == manifest["id"]
    assert proof.source_sha256 == manifest["record"]["source_file_sha256"]
    assert proof.observed_m1_sha256 == manifest["record"]["observed_quote_sha256"]
    assert proof.rows == 3
    assert proof.execution == "NONE"
    assert not proof.lineage_verified  # two independently supplied objects, not proven same producer
    assert not proof.gaps_audited
    assert not proof.strategy_implementation_verified
    assert not proof.independent_oos
    assert not proof.profitability_verified


@pytest.mark.parametrize("suffix", [".json", ".csv"])
def test_direct_file_loader_recomputes_exact_source_to_quote_lineage(tmp_path, suffix):
    src, _, manifest, proposal = fixtures(tmp_path, suffix=suffix)
    proof = preflight_direct_gold_m1_file(
        proposal, manifest, original_m1_file=src, observed_engine_commit=HEAD,
    )
    assert proof.lineage_verified is True
    assert proof.public_metadata()["lineage_verified"] is True
    assert proof.public_metadata()["execution"] == "NONE"
    assert proof.public_metadata()["profitability_verified"] is False
    assert proof.public_metadata()["source_authentication"] == "NOT_VERIFIED"
    assert proof.public_metadata()["gaps_audited"] is False


def test_repeated_import_of_identical_bytes_is_deterministic(tmp_path):
    src, _, manifest, proposal = fixtures(tmp_path)
    a = preflight_direct_gold_m1_file(proposal, manifest, original_m1_file=src, observed_engine_commit=HEAD)
    b = preflight_direct_gold_m1_file(proposal, manifest, original_m1_file=src, observed_engine_commit=HEAD)
    assert a == b


def test_ask_quote_revision_is_detected_before_any_research_execution(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    forged = frame.copy()
    forged.loc[forged.index[0], "ac"] += 0.03
    with pytest.raises(ValueError, match="fingerprint changed"):
        preflight(src, forged, manifest, proposal)


def test_raw_source_revision_is_detected_even_if_frame_stays_unchanged(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    src.write_bytes(src.read_bytes() + b" \n")
    with pytest.raises(ValueError, match="bytes differ"):
        preflight(src, frame, manifest, proposal)


def test_identical_market_quotes_with_different_raw_bytes_require_new_manifest(tmp_path):
    src, _, manifest, proposal = fixtures(tmp_path)
    src.write_text(json.dumps(data_rows(), indent=2), encoding="utf-8")
    assert fingerprint_loaded_m1(read_source(src)) == manifest["record"]["observed_quote_sha256"]
    with pytest.raises(ValueError, match="bytes differ"):
        preflight_direct_gold_m1_file(proposal, manifest, original_m1_file=src, observed_engine_commit=HEAD)


def test_preflight_fails_on_wrong_dataset_hash_even_with_matching_file(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    proposal["dataset_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="not bound"):
        preflight(src, frame, manifest, proposal)


def test_wrong_engine_commit_is_not_allowed(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    with pytest.raises(ValueError, match="checkout differs"):
        preflight(src, frame, manifest, proposal, head="f"*40)


def test_non_sha_git_identity_is_rejected(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    with pytest.raises(ValueError, match="exact SHA"):
        preflight(src, frame, manifest, proposal, head="mutable-branch")


def test_observation_count_is_not_trusted_from_manifest(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    changed = frame.iloc[:-1].copy()
    with pytest.raises(ValueError, match="row count"):
        preflight(src, changed, manifest, proposal)


def test_reordered_frame_is_not_accepted(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    changed = frame.iloc[::-1].copy()
    with pytest.raises(ValueError, match="unique sorted UTC"):
        preflight(src, changed, manifest, proposal)


def test_crossed_bidask_is_rejected_even_if_manifest_fingerprint_matches_old(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    corrupted = frame.copy()
    corrupted.loc[corrupted.index[0], "ao"] = 1
    with pytest.raises(ValueError, match="crossed BID/ASK"):
        preflight(src, corrupted, manifest, proposal)


def test_source_metadata_tamper_is_rejected(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    m = deepcopy(manifest)
    m["record"]["rows"] = 500
    with pytest.raises(ValueError, match="identity mismatch"):
        preflight(src, frame, m, proposal)


def test_wrong_asset_and_cross_feed_rejected(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    forged = deepcopy(manifest)
    forged["record"]["family"] = "private_terminal_bidask_ticks"
    with pytest.raises(ValueError):
        preflight(src, frame, forged, proposal)


@pytest.mark.parametrize("range_adjust,error", [
    ({"window_start_utc":"2024-01-01T23:59:00Z"},"before the available"),
    ({"window_end_exclusive_utc":"2024-01-02T00:04:00Z"},"unobserved future"),
    ({"window_start_utc":"2024-01-02T00:03:00Z","window_end_exclusive_utc":"2024-01-02T00:04:00Z"},"unobserved future"),
])
def test_no_historical_window_leakage(tmp_path, range_adjust, error):
    src, frame, manifest, proposal = fixtures(tmp_path)
    proposal.update(range_adjust)
    with pytest.raises(ValueError, match=error):
        preflight(src, frame, manifest, proposal)


def test_no_raw_quotes_or_original_sha_in_public_report(tmp_path):
    src, frame, manifest, proposal = fixtures(tmp_path)
    proof = preflight(src, frame, manifest, proposal)
    summary = json.dumps(proof.public_metadata())
    assert "2000." not in summary
    assert proof.observed_m1_sha256 not in summary
    assert proof.source_sha256 not in summary
    assert str(src) not in summary
    assert summary.count("approved_for_live") == 1


def test_parquet_and_zip_are_not_direct_lineage_proofs(tmp_path):
    src, _, manifest, proposal = fixtures(tmp_path)
    for suffix in (".zip", ".parquet", ".exe"):
        other = tmp_path / ("source" + suffix)
        other.write_bytes(src.read_bytes())
        with pytest.raises(ValueError, match="JSON/CSV"):
            preflight_direct_gold_m1_file(proposal, manifest, original_m1_file=other, observed_engine_commit=HEAD)


def test_direct_file_limit_rejected_before_read(tmp_path):
    src, _, manifest, proposal = fixtures(tmp_path)
    src.write_bytes(b"")
    with pytest.raises(ValueError, match="empty or oversized"):
        preflight_direct_gold_m1_file(proposal, manifest, original_m1_file=src, observed_engine_commit=HEAD)


def test_local_git_head_and_clean_tracked_checkout(tmp_path):
    root = tmp_path / "engine_repo"
    root.mkdir()
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    git("init")
    git("config", "user.name", "Synthetic CI")
    git("config", "user.email", "synthetic-ci@example.invalid")
    file = root / "tracked.txt"
    file.write_text("frozen\n", encoding="utf-8")
    git("add", "tracked.txt")
    git("commit", "-m", "frozen fixture")
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    assert inspect_local_checkout(root) == head
    file.write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="modified tracked"):
        inspect_local_checkout(root)


def test_git_subdirectory_does_not_masquerade_as_root(tmp_path):
    root = tmp_path / "engine_repo"
    root.mkdir()
    subprocess.run(["git","-C",str(root),"init"],check=True,capture_output=True)
    nested = root / "subfolder"
    nested.mkdir()
    with pytest.raises(ValueError, match="top-level"):
        inspect_local_checkout(nested)


def test_private_cli_direct_source_round_trip_without_quotes(tmp_path, capsys, monkeypatch):
    from scripts import preflight_ai_research_source as cli
    src, frame, manifest, proposal = fixtures(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    manifest_path = tmp_path / "manifest.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(cli, "inspect_local_checkout", lambda root: HEAD)
    assert cli.main([
        "--proposal",str(proposal_path),
        "--source-manifest",str(manifest_path),
        "--original-m1",str(src),
        "--checkout",str(tmp_path)
    ]) == 0
    public = json.loads(capsys.readouterr().out)
    assert public["lineage_verified"] is True
    assert public["profitability_verified"] is False
    assert "2000." not in str(public)
    assert "original_source_file" not in str(public)


def test_cli_rejects_broker_scope_and_malformed_nonfinite_json(tmp_path, capsys, monkeypatch):
    from scripts import preflight_ai_research_source as cli
    src, _, manifest, proposal = fixtures(tmp_path)
    p = tmp_path / "proposal.json"
    m = tmp_path / "manifest.json"
    p.write_text(json.dumps(proposal)[:-1] + ', "password":"hidden"}', encoding="utf-8")
    m.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(cli,"inspect_local_checkout",lambda root: HEAD)
    with pytest.raises(SystemExit) as e:
        cli.main(["--proposal",str(p),"--source-manifest",str(m),
                  "--original-m1",str(src),"--checkout",str(tmp_path)])
    assert e.value.code == 2
    output = capsys.readouterr()
    assert "hidden" not in output.err
    assert str(src) not in output.err
