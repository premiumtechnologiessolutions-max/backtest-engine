"""Synthetic integrity regression for immutable local research queue bytes.

All modifications below preserve the parsed request's fingerprint and
semantics; they must still fail because the *persisted* record changed.
"""
import json

import pytest

from scripts.research_job_queue import enqueue, frozen_request, list_jobs


def _stored(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "research").mkdir()
    (tmp_path / "docs" / "FAC024.md").write_text("PREREGISTERED\n")
    (tmp_path / "research" / "strategy_factory_registry.json").write_text(
        '{"completed_batches":[]}', encoding="utf-8")
    record = frozen_request(tmp_path, "NRF-FAC-024", "docs/FAC024.md",
                            "a" * 40, "2026-01-01", "2026-01-31")
    enqueue(tmp_path, record)
    path = tmp_path / "reports" / "research_jobs" / (
        record["fingerprint"] + ".json")
    return record, path


@pytest.mark.parametrize("mutation", [
    "duplicate_status", "pretty_json", "extra_newline",
    "windows_line_ending", "leading_whitespace",
])
def test_rejects_semantically_identical_but_noncanonical_queue_bytes(
        tmp_path, mutation):
    record, path = _stored(tmp_path)
    original = path.read_bytes()
    if mutation == "duplicate_status":
        target = b'"status":"QUEUED_NOT_EXECUTED"'
        assert target in original
        forged = original.replace(
            target, target + b',"status":"QUEUED_NOT_EXECUTED"', 1)
    elif mutation == "pretty_json":
        forged = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
    elif mutation == "extra_newline":
        forged = original + b"\n"
    elif mutation == "windows_line_ending":
        forged = original.replace(b"\n", b"\r\n")
    else:
        forged = b" " + original
    assert forged != original
    path.write_bytes(forged)
    with pytest.raises(ValueError, match="Noncanonical immutable queue"):
        list_jobs(tmp_path)
    # Even existing-request idempotence cannot silently bless forged bytes.
    with pytest.raises(ValueError, match="differs"):
        enqueue(tmp_path, record)


def test_unmodified_queue_record_still_loads(tmp_path):
    record, _ = _stored(tmp_path)
    assert list_jobs(tmp_path) == [record]
