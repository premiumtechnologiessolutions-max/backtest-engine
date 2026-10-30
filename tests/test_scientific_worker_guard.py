"""B13: no actual historical replay for a B11-rejected canonical strategy."""
from __future__ import annotations
from datetime import datetime,timezone
import os
import pytest
from norisk_quant.research_control_plane import ResearchQueue,SCHEMA,EXTERNAL_SOURCE
from norisk_quant.scientific_rejection_registry import ScientificDecisionJournal
from norisk_quant.canonical_research_worker import execute_one_approved_job
from tests.test_scientific_rejection_registry import plan,evidence

@pytest.mark.skipif(os.name!="posix",reason="POSIX private research only")
def test_rejected_strategy_fails_before_original_market_source_preflight(tmp_path,monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    private=tmp_path/"private"
    private.mkdir();private.chmod(0o700)
    scientific=ScientificDecisionJournal(private/"science.sqlite3")
    historical=plan(private)
    scientific.append(evidence(historical,2012))
    candidate={"schema":SCHEMA,"producer":EXTERNAL_SOURCE,"agent":"nova",
               "campaign_id":"brand_new_name_without_new_math","asset":"XAUUSD",
               "dataset_sha256":"a"*64,"engine_commit":"b"*40,
               "strategy_id":"m1-sweep","parameters":historical["jobs"][0]["parameters"],
               "timeframe":"M1","window_start_utc":"2024-01-01T00:00:00Z",
               "window_end_exclusive_utc":"2024-02-01T00:00:00Z",
               "quantity_ounces":1.0,"fee_all_in_per_ounce":0.4,
               "execution_mode":"m1_conservative","exposure_context":"historical_exposed"}
    queue=ResearchQueue(private/"queue.sqlite3")
    job=queue.submit(candidate,now=datetime(2026,10,30,tzinfo=timezone.utc))
    queue.set_paused(False,now=datetime(2026,10,30,0,0,1,tzinfo=timezone.utc))
    source=private/"Gold.zip";source.write_bytes(b"synthetic dummy only");source.chmod(0o600)
    output=private/"results";output.mkdir();output.chmod(0o700)
    def must_not_execute(*args,**kwargs):
        raise AssertionError("Original prices must never be loaded after scientific rejection")
    monkeypatch.setattr(worker,"preflight_queued_research",must_not_execute)
    with pytest.raises(ValueError,match="Previously rejected identical"):
        execute_one_approved_job(queue,source_manifest={},data_zip=source,
                                 checkout=private,output_root=output,
                                 scientific_journal=scientific)
    assert queue.status(job)["state"]=="rejected"
    assert not list(output.iterdir())

@pytest.mark.skipif(os.name!="posix",reason="POSIX private research only")
def test_operator_cli_execute_refuses_missing_science_journal(tmp_path,capsys):
    from scripts.canonical_research_worker import main
    private=tmp_path/"private";private.mkdir();private.chmod(0o700)
    queue=ResearchQueue(private/"queue.sqlite3")
    with pytest.raises(SystemExit) as failure:
        main(["--queue-db",str(queue.path),"--execute"])
    assert failure.value.code==2
    assert queue.counts()["paused"] is True
    assert "password" not in capsys.readouterr().err
