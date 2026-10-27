"""Synthetic-only tests: research requests must never execute market jobs."""
import json
import os
from pathlib import Path

import pytest

from scripts.research_job_queue import (
    enqueue, frozen_request, list_jobs, main, _canonical, _sha,
)


def root_fixture(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "research").mkdir()
    (tmp_path / "docs" / "FAC024_FROZEN.md").write_text("Frozen before outcomes\n")
    (tmp_path / "research" / "strategy_factory_registry.json").write_text('{"completed_batches":[]}')
    return tmp_path


def request(root):
    return frozen_request(root, "NRF-FAC-024", "docs/FAC024_FROZEN.md",
                          "a" * 40, "2026-11-01", "2027-10-31")


def test_intake_is_idempotent_and_does_not_execute(tmp_path):
    root = root_fixture(tmp_path)
    job = request(root)
    assert enqueue(root, job) == job
    assert enqueue(root, job) == job
    assert list_jobs(root) == [job]
    assert job["status"] == "QUEUED_NOT_EXECUTED"
    assert len(list((root / "reports" / "research_jobs").iterdir())) == 1
    if os.name == "posix":
        assert (root / "reports" / "research_jobs").stat().st_mode & 0o077 == 0
        assert next((root / "reports" / "research_jobs").iterdir()).stat().st_mode & 0o077 == 0


def test_fingerprint_binds_source_registry_and_commit(tmp_path):
    root = root_fixture(tmp_path)
    original = request(root)
    (root / "docs" / "FAC024_FROZEN.md").write_text("Different source")
    assert request(root)["fingerprint"] != original["fingerprint"]
    (root / "research" / "strategy_factory_registry.json").write_text('{"completed_batches":[1]}')
    assert request(root)["fingerprint"] != original["fingerprint"]
    assert frozen_request(root, "NRF-FAC-024", "docs/FAC024_FROZEN.md",
                          "b" * 40, "2026-11-01", "2027-10-31")["fingerprint"] != request(root)["fingerprint"]


@pytest.mark.parametrize("path", [
    "../private.zip", "docs/../private.zip", "docs/../../secret.md",
    "/tmp/file.md", "docs/quote.zip", "docs\\file.md",
    "https://example.org/test.md", "research/.git/../secret.json",
])
def test_rejects_unsafe_source_paths(tmp_path, path):
    root = root_fixture(tmp_path)
    with pytest.raises(ValueError):
        frozen_request(root, "NRF-FAC-024", path, "a" * 40,
                       "2026-11-01", "2027-10-31")


@pytest.mark.parametrize("family,commit,start,end", [
    ("../../etc", "a" * 40, "2026-11-01", "2027-10-31"),
    ("NRF-FAC-024", "x" * 40, "2026-11-01", "2027-10-31"),
    ("NRF-FAC-024", "a" * 40, "2026-11-1", "2027-10-31"),
    ("NRF-FAC-024", "a" * 40, "2027-11-01", "2026-10-31"),
])
def test_rejects_invalid_job_identity_or_dates(tmp_path, family, commit, start, end):
    root = root_fixture(tmp_path)
    with pytest.raises(ValueError):
        frozen_request(root, family, "docs/FAC024_FROZEN.md", commit, start, end)


def test_tampered_job_record_fails_closed(tmp_path):
    root = root_fixture(tmp_path)
    job = enqueue(root, request(root))
    file = root / "reports" / "research_jobs" / (job["fingerprint"] + ".json")
    modified = {**job, "status": "COMPLETED"}
    file.write_text(json.dumps(modified))
    with pytest.raises(ValueError, match="state"):
        list_jobs(root)


def test_forged_fingerprint_fails_closed(tmp_path):
    root = root_fixture(tmp_path)
    job = enqueue(root, request(root))
    file = root / "reports" / "research_jobs" / (job["fingerprint"] + ".json")
    modified = {**job, "family": "NRF-FAC-099"}
    file.write_text(json.dumps(modified))
    with pytest.raises(ValueError, match="Tampered"):
        list_jobs(root)


def test_existing_job_cannot_be_replaced(tmp_path):
    root = root_fixture(tmp_path)
    job = enqueue(root, request(root))
    file = root / "reports" / "research_jobs" / (job["fingerprint"] + ".json")
    file.write_text("tampered")
    with pytest.raises(ValueError, match="differs"):
        enqueue(root, job)


def test_symlinked_spec_is_rejected(tmp_path):
    root = root_fixture(tmp_path)
    (root / "docs" / "link.md").symlink_to(root / "docs" / "FAC024_FROZEN.md")
    with pytest.raises(ValueError, match="symlinked"):
        frozen_request(root, "NRF-FAC-024", "docs/link.md", "a" * 40,
                       "2026-11-01", "2027-10-31")


def test_no_queue_means_empty_not_completed(tmp_path):
    root = root_fixture(tmp_path)
    assert list_jobs(root) == []
    assert not (root / "reports").exists()
