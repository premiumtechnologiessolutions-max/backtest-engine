"""Synthetic provenance binding tests: no third-party execution."""
import copy
import hashlib

import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.research_job_queue import _canonical
from norisk_quant.external_research_bridge import result_receipt
from norisk_quant.external_queue_binding import (
    bind_claim, verify_binding, bind_unverified_receipt,
)


def frozen():
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/example.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40, "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31", "status": "QUEUED_NOT_EXECUTED",
    }
    return {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}


def claimed(tmp_path):
    record = frozen()
    state = DurableResearchState(tmp_path / "research.sqlite3")
    state.ingest_record(record)
    claim = state.claim_next("worker-A", now_ms=1000)
    return record, claim, state


def build(record, claim):
    return bind_claim(record, claim, engine="lean", source_sha256="3" * 64,
                      code_sha256="4" * 64)


def test_real_durable_claim_maps_to_external_request(tmp_path):
    record, claim, state = claimed(tmp_path)
    binding = build(record, claim)
    assert verify_binding(record, claim, binding) == binding
    assert binding["external_request"]["spec_sha256"] == record["frozen_spec_sha256"]
    assert binding["external_request"]["experiment_id"].startswith("exp_")
    assert binding["execution_authorized"] is False
    assert state.status(record["fingerprint"])["state"] == "RUNNING"


def test_claim_substitution_and_modified_queue_fail_closed(tmp_path):
    record, claim, _ = claimed(tmp_path)
    binding = build(record, claim)
    tampered = copy.deepcopy(claim)
    tampered["fencing_token"] += 1
    with pytest.raises(ValueError, match="mismatch"):
        verify_binding(record, tampered, binding)
    modified = dict(record, frozen_spec_sha256="9" * 64)
    with pytest.raises(ValueError, match="Tampered"):
        verify_binding(modified, claim, binding)


def test_external_request_substitution_and_unsafe_flag_rejected(tmp_path):
    record, claim, _ = claimed(tmp_path)
    binding = build(record, claim)
    for field, value in [("result_accepted", True),
                         ("execution_authorized", True)]:
        broken = dict(binding, **{field: value})
        with pytest.raises(ValueError, match="mismatch"):
            verify_binding(record, claim, broken)
    broken = copy.deepcopy(binding)
    broken["external_request"]["engine"] = "finrl"
    with pytest.raises(ValueError):
        verify_binding(record, claim, broken)


def test_receipt_bound_but_not_accepted(tmp_path):
    record, claim, state = claimed(tmp_path)
    binding = build(record, claim)
    artifact = "5" * 64
    receipt = result_receipt(binding["external_request"],
                             provider_build_sha256="6" * 64,
                             artifact_sha256=artifact, status="completed_unverified")
    result = bind_unverified_receipt(record, claim, binding, receipt,
                                     actual_artifact_sha256=artifact)
    assert result["accepted"] is False
    assert state.status(record["fingerprint"])["state"] == "RUNNING"
    with pytest.raises(ValueError, match="not bound"):
        bind_unverified_receipt(record, claim, binding, receipt,
                                actual_artifact_sha256="7" * 64)


def test_reclaimed_lease_cannot_use_prior_binding(tmp_path):
    record, claim, state = claimed(tmp_path)
    binding = build(record, claim)
    assert state.requeue_expired(record["fingerprint"],
                                 process_exit_confirmed=True, now_ms=121001)
    new_claim = state.claim_next("worker-B", now_ms=121001)
    with pytest.raises(ValueError, match="mismatch"):
        verify_binding(record, new_claim, binding)
    assert verify_binding(record, new_claim, build(record, new_claim))
