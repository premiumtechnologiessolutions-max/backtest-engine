"""Crash/concurrency publication assertions for immutable research queue."""
import os
from pathlib import Path
import pytest

from scripts import research_job_queue as queue


def fixture(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "research").mkdir()
    (tmp_path / "docs" / "FROZEN.md").write_text("freeze")
    (tmp_path / "research" / "strategy_factory_registry.json").write_text("{}")
    request = queue.frozen_request(
        tmp_path, "NRF-FAC-024", "docs/FROZEN.md", "a" * 40,
        "2026-11-01", "2027-10-31")
    return request


@pytest.mark.skipif(os.name != "posix", reason="os.link publication contract is POSIX")
def test_final_job_name_not_visible_until_complete_payload(tmp_path, monkeypatch):
    request = fixture(tmp_path)
    target = (tmp_path / "reports" / "research_jobs"
              / (request["fingerprint"] + ".json"))
    original_link = os.link

    def observed_link(src, dst, *args, **kwargs):
        assert dst == target
        assert not target.exists()
        assert Path(src).read_bytes() == queue._canonical(request) + b"\\n"
        return original_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(queue.os, "link", observed_link)
    assert queue.enqueue(tmp_path, request) == request
    assert queue.list_jobs(tmp_path) == [request]
    assert queue.enqueue(tmp_path, request) == request
    assert list(target.parent.glob(".research-job-*.tmp")) == []


def test_stale_internal_staging_never_counts_as_committed_job(tmp_path):
    request = fixture(tmp_path)
    path = tmp_path / "reports" / "research_jobs"
    path.mkdir(parents=True)
    (path / ".research-job-crash123.tmp").write_bytes(b'{"incomplete":')
    assert queue.list_jobs(tmp_path) == []
    assert queue.enqueue(tmp_path, request) == request
    assert queue.list_jobs(tmp_path) == [request]


def test_noncanonical_final_job_is_not_silently_replaced(tmp_path):
    request = fixture(tmp_path)
    path = tmp_path / "reports" / "research_jobs"
    path.mkdir(parents=True)
    (path / (request["fingerprint"] + ".json")).write_bytes(b'{"partial":')
    with pytest.raises(ValueError, match="differs"):
        queue.enqueue(tmp_path, request)
