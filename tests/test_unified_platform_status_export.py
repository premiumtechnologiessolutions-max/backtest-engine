"""B08 private operator status snapshot: no DB writes, raw quotes, or public leaks."""
from __future__ import annotations

from datetime import datetime,timezone
import hashlib
import json
import os

import pytest

from norisk_quant.research_control_plane import ResearchQueue
from norisk_quant.unified_research_platform import (
    ExistingResearchQueueStatus,UnifiedResearchPlatform,
)
from norisk_quant.source_registry import register_original_gold_m1
from scripts.export_unified_platform_status import build_operator_snapshot,main

POSIX=pytest.mark.skipif(os.name!="posix",reason="Private owner-only exporter is POSIX-only")


def fixture(tmp_path):
    directory=tmp_path/"private"
    directory.mkdir()
    if os.name=="posix":
        directory.chmod(0o700)
    db=directory/"research.sqlite3"
    queue=ResearchQueue(db)
    manifest=register_original_gold_m1({
        "origin":"user_supplied_gold_m1_bidask",
        "source_file_sha256":"a"*64,
        "observed_slice_sha256":"b"*64,
        "rows":28622,
        "first_utc":"2012-01-02T23:00:00+00:00",
        "last_utc":"2012-01-31T23:59:00+00:00",
    }).internal_manifest()
    src=directory/"private_original_month.json"
    src.write_text(json.dumps(manifest),encoding="utf-8")
    out=directory/"operator_only_status.json"
    return directory,db,queue,src,out


@POSIX
def test_readonly_queue_status_never_modifies_database(tmp_path):
    directory,db,queue,source,out=fixture(tmp_path)
    before=hashlib.sha256(db.read_bytes()).hexdigest()
    state=ExistingResearchQueueStatus(db)
    assert state.counts()["paused"] is True
    assert state.counts()["queued"]==0
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before


@POSIX
def test_valid_private_source_manifest_and_queue_status_offline(tmp_path,capsys):
    _,db,queue,src,out=fixture(tmp_path)
    assert main(["--queue-db",str(db),"--source-manifest",str(src),"--out",str(out)])==0
    payload=json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"]=="NRFX_UNIFIED_RESEARCH_PLATFORM_OPERATOR_V1"
    assert payload["data_hub"]["registered_metadata_sources"]==1
    assert payload["data_hub"]["sources"][0]["family"]=="original_gold_m1_bidask"
    assert payload["research_control"]["counts"]["paused"] is True
    assert payload["execution"]["mt5_order_connection"] is False
    assert payload["execution"]["profitability_verified"] is False
    assert payload["review_gates"]["private_operator_authentication"]=="NOT_IMPLEMENTED_BY_THIS_VIEW"
    assert out.stat().st_mode & 0o077==0
    logs=capsys.readouterr()
    assert "a"*64 not in logs.out
    assert str(src) not in logs.out


@POSIX
def test_private_status_does_not_expose_internal_source_hashes(tmp_path):
    _,db,queue,src,out=fixture(tmp_path)
    payload=build_operator_snapshot(db,source_manifests=[src])
    displayed=json.dumps(payload,sort_keys=True)
    for term in ("a"*64,"b"*64,"source_file_sha256","observed_quote_sha256","password"):
        assert term not in displayed


@POSIX
def test_export_cannot_overwrite_existing_status_snapshot(tmp_path):
    _,db,queue,src,out=fixture(tmp_path)
    out.write_text("original owner data",encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--queue-db",str(db),"--source-manifest",str(src),"--out",str(out)])
    assert exc.value.code==2
    assert out.read_text(encoding="utf-8")=="original owner data"


@POSIX
def test_empty_or_nonexistent_queue_not_initialized_for_export(tmp_path):
    directory=tmp_path/"private"
    directory.mkdir(mode=0o700)
    db=directory/"not_created.sqlite3"
    out=directory/"never.json"
    with pytest.raises(SystemExit) as exc:
        main(["--queue-db",str(db),"--out",str(out)])
    assert exc.value.code==2
    assert not db.exists()
    assert not out.exists()


@POSIX
def test_public_directory_is_rejected_without_writing(tmp_path):
    _,db,queue,src,out=fixture(tmp_path)
    public=tmp_path/"public"
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    target=public/"operator_status.json"
    with pytest.raises(SystemExit) as exc:
        main(["--queue-db",str(db),"--source-manifest",str(src),"--out",str(target)])
    assert exc.value.code==2
    assert not target.exists()


@POSIX
def test_operator_status_does_not_resume_private_queue(tmp_path):
    _,db,queue,src,out=fixture(tmp_path)
    assert queue.counts()["paused"] is True
    main(["--queue-db",str(db),"--source-manifest",str(src),"--out",str(out)])
    assert ResearchQueue(db).counts()["paused"] is True


@POSIX
def test_malformed_manifest_does_not_initialize_output(tmp_path):
    _,db,queue,src,out=fixture(tmp_path)
    content=json.loads(src.read_text(encoding="utf-8"))
    content["record"]["execution"]="LIVE"
    src.write_text(json.dumps(content),encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--queue-db",str(db),"--source-manifest",str(src),"--out",str(out)])
    assert not out.exists()


def test_readonly_queue_uses_strict_known_status_values(tmp_path):
    _,db,queue,src,out=fixture(tmp_path)
    assert ExistingResearchQueueStatus(db).counts()["paused"] is True
    assert isinstance(UnifiedResearchPlatform(queue=ExistingResearchQueueStatus(db)),UnifiedResearchPlatform)
