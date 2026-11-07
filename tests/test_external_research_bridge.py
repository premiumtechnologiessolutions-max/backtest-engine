"""Synthetic contract tests; no third-party engine or private Gold data."""
import copy
import hashlib

import pytest

from norisk_quant.external_research_bridge import (
    request, result_receipt, verify_request, verify_result,
)


def h(data):
    return hashlib.sha256(data).hexdigest()


def req(engine="lean"):
    return request(engine, source_sha256=h(b"private source"),
                   code_sha256=h(b"frozen code"), spec_sha256=h(b"spec"),
                   dataset="xauusd_m1", experiment_id="frozen_001")


@pytest.mark.parametrize("engine", ["lean", "nautilus", "openbb", "rd_agent",
                                    "tradingagents", "finrl", "external_python",
                                    "norisk_quant"])
def test_offline_contract_provider_allowlist(engine):
    assert verify_request(req(engine))["engine"] == engine


def test_tampered_request_or_live_scope_is_rejected():
    for field, value in [("scope", "live_trading"),
                         ("code_sha256", h(b"changed code")),
                         ("shell_command", "echo unsafe")]:
        changed = copy.deepcopy(req())
        changed[field] = value
        with pytest.raises(ValueError):
            verify_request(changed)


def test_invalid_hash_and_unknown_provider_fail_closed():
    with pytest.raises(ValueError):
        req("unknown")
    with pytest.raises(ValueError):
        request("lean", source_sha256="not-a-sha", code_sha256=h(b"code"),
                spec_sha256=h(b"spec"), dataset="gold", experiment_id="exp_1")


def test_receipt_round_trip_binds_actual_artifact_digest():
    frozen = req("nautilus")
    artifact = h(b"synthetic result bytes")
    receipt = result_receipt(frozen, provider_build_sha256=h(b"version"),
                             artifact_sha256=artifact,
                             status="completed_unverified")
    assert verify_result(frozen, receipt, actual_artifact_sha256=artifact) == receipt
    assert receipt["accepted"] is False


def test_receipt_substitution_and_self_approval_rejected():
    frozen = req()
    artifact = h(b"result bytes")
    receipt = result_receipt(frozen, provider_build_sha256=h(b"build"),
                             artifact_sha256=artifact,
                             status="completed_unverified")
    with pytest.raises(ValueError):
        verify_result(frozen, receipt, actual_artifact_sha256=h(b"tampered"))
    tampered = dict(receipt, accepted=True)
    with pytest.raises(ValueError):
        verify_result(frozen, tampered, actual_artifact_sha256=artifact)
    with pytest.raises(ValueError):
        result_receipt(frozen, provider_build_sha256=h(b"build"),
                       artifact_sha256=artifact, status="accepted")


def test_cross_engine_receipt_not_reusable():
    artifact = h(b"artifact")
    receipt = result_receipt(req("lean"), provider_build_sha256=h(b"version"),
                             artifact_sha256=artifact,
                             status="completed_unverified")
    with pytest.raises(ValueError):
        verify_result(req("finrl"), receipt, actual_artifact_sha256=artifact)
