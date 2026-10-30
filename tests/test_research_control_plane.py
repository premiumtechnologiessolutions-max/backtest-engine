"""Fail-closed B04 AI Quant Lab -> canonical XAUUSD research queue regressions."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from norisk_quant.registry import ExperimentIdentity, fingerprint
from norisk_quant.research_control_plane import (
    EXTERNAL_SOURCE, MAX_ACTIVE, MAX_ATTEMPTS, SCHEMA,
    Lease, ResearchQueue, proposal_identity, proposal_from_aiquantlab_hypothesis,
)

UTC = timezone.utc
EPOCH = datetime(2026, 10, 30, 1, 0, tzinfo=UTC)
HEX64 = "a" * 64
HEX40 = "b" * 40


def t(seconds=0):
    return EPOCH + timedelta(seconds=seconds)


def hypothesis(*, agent="nova", campaign="sample-campaign", lookback=20):
    return {
        "schema": SCHEMA, "producer": EXTERNAL_SOURCE,
        "agent": agent, "campaign_id": campaign, "asset": "XAUUSD",
        "dataset_sha256": HEX64, "engine_commit": HEX40,
        "strategy_id": "math_formula_v1", "parameters": {"lookback": lookback, "threshold": 0.4},
        "timeframe": "M1", "window_start_utc": "2025-01-01T00:00:00Z",
        "window_end_exclusive_utc": "2025-07-01T00:00:00Z",
        "quantity_ounces": 1.0, "fee_all_in_per_ounce": 0.40,
        "execution_mode": "m1_conservative",
        "exposure_context": "historical_exposed",
    }


def queue(tmp_path):
    return ResearchQueue(tmp_path / "control.sqlite3")


def finish_result():
    return {"disposition": "proposal_recorded", "reason_code": "audit_pending", "evidence_sha256": "f" * 64}


def test_aiquantlab_intent_is_exact_canonical_experiment_identity():
    x = hypothesis()
    actual, body, agent = proposal_identity(x)
    canonical = ExperimentIdentity(
        dataset_sha256=HEX64, engine_commit=HEX40, strategy_id="math_formula_v1",
        parameters=x["parameters"], timeframe="M1",
        window_start_utc="2025-01-01T00:00:00+00:00",
        window_end_exclusive_utc="2025-07-01T00:00:00+00:00",
        quantity_ounces=1.0, fee_all_in_per_ounce=0.40,
        execution_mode="m1_conservative", exposure_context="historical_exposed",
    )
    assert actual == fingerprint(canonical)
    assert json.loads(body)["canonical_experiment_id"] == actual
    assert agent == "nova"


def test_equivalent_explicit_utc_forms_cannot_create_duplicate_experiments(tmp_path):
    first = hypothesis()
    second = hypothesis(agent="forge", campaign="second-campaign")
    second["window_start_utc"] = "2025-01-01T00:00:00.000000+00:00"
    second["window_end_exclusive_utc"] = "2025-07-01T00:00:00+00:00"
    assert proposal_identity(first)[0] == proposal_identity(second)[0]
    q = queue(tmp_path)
    assert q.submit(first, now=t()) == q.submit(second, now=t(1))
    assert q.counts()["queued"] == 1


def test_agents_cannot_multiply_same_experiment_by_campaign_or_agent(tmp_path):
    q = queue(tmp_path)
    first = q.submit(hypothesis(), now=t())
    duplicate = q.submit(hypothesis(agent="forge", campaign="another-campaign"), now=t(1))
    assert duplicate == first
    assert q.counts()["queued"] == 1
    assert q.audit(first) == ({"event_type": "submitted", "attempt": 0, "occurred_utc": t().isoformat(timespec="microseconds")},)


def test_changed_strategy_parameters_or_source_digest_create_distinct_jobs(tmp_path):
    q = queue(tmp_path)
    a = hypothesis()
    b = hypothesis(lookback=21)
    c = hypothesis()
    c["dataset_sha256"] = "e" * 64
    assert len({q.submit(a, now=t()), q.submit(b, now=t(1)), q.submit(c, now=t(2))}) == 3


@pytest.mark.parametrize("change,err", [
    ({"agent": "atlas"}, "Nova/Forge"),
    ({"agent": "chronos"}, "Nova/Forge"),
    ({"agent": "sentinel"}, "Nova/Forge"),
    ({"producer": "untrusted-web"}, "producer"),
    ({"schema": "NRFX_BROKER_ORDERS"}, "producer"),
    ({"asset": "EURUSD"}, "XAUUSD"),
    ({"dataset_sha256": "opaque"}, "dataset"),
    ({"engine_commit": "mutable-main"}, "engine commit"),
    ({"timeframe": "TICK"}, "timeframe"),
    ({"execution_mode": "observed_tick_research"}, "conservative"),
    ({"execution_mode": "live"}, "conservative"),
    ({"exposure_context": "future_prospective"}, "future prospective"),
    ({"exposure_context": "verified_oos"}, "future prospective"),
    ({"fee_all_in_per_ounce": 0.1}, "0.40"),
    ({"fee_all_in_per_ounce": float("nan")}, "0.40"),
    ({"quantity_ounces": True}, "quantity"),
    ({"quantity_ounces": 0}, "quantity"),
    ({"quantity_ounces": 100.01}, "quantity"),
    ({"window_start_utc": "2025-01-01T03:00:00+03:00"}, "UTC"),
    ({"window_start_utc": "2026-01-01T00:00:00Z"}, "interval"),
    ({"strategy_id": "os.system('test')"}, "strategy"),
    ({"campaign_id": "../secrets"}, "campaign"),
    ({"parameters": {"lookback": True}}, "Parameters"),
    ({"parameters": {"lookback": float("inf")}}, "Parameters"),
    ({"parameters": {"pay": {"token": "secret"}}}, "Parameters"),
    ({"parameters": {"foo": "raise Exception()"}}, "Parameters"),
    ({"parameters": {"lot": 1e9}}, "Parameters"),
])
def test_ai_hypotheses_cannot_override_data_authority_or_execute(change, err):
    p = hypothesis()
    p.update(change)
    with pytest.raises(ValueError, match=err):
        proposal_identity(p)


def test_unknown_proposal_fields_never_become_authorizations():
    for name in ("approved_for_live", "order_send", "quant_score", "profit", "password", "raw_ticks"):
        p = hypothesis()
        p[name] = 9999
        with pytest.raises(ValueError, match="schema mismatch"):
            proposal_identity(p)


def test_parameters_reject_code_strings_and_oversized_shape():
    p = hypothesis()
    p["parameters"] = {f"p_{i}": i for i in range(25)}
    with pytest.raises(ValueError, match="bounded"):
        proposal_identity(p)


def test_operator_starts_paused_and_no_task_can_start_until_manual_resume(tmp_path):
    q = queue(tmp_path)
    id_ = q.submit(hypothesis(), now=t())
    assert q.counts()["paused"] is True
    assert q.claim(worker="worker_1", now=t(2)) is None
    assert q.status(id_)["state"] == "queued"
    q.set_paused(False, now=t(3))
    lease = q.claim(worker="worker_1", now=t(4))
    assert lease is not None and lease.attempt == 1
    assert q.status(id_)["state"] == "leased"


def test_lease_is_redacted_and_success_never_proves_profit(tmp_path):
    q = queue(tmp_path)
    job = q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    lease = q.claim(worker="worker_1", now=t(2))
    assert lease is not None
    assert lease.token not in repr(lease)
    assert "REDACTED" in repr(lease)
    assert q.finish(lease, now=t(3), result=finish_result()) is True
    assert q.finish(lease, now=t(4), result=finish_result()) is False
    record = q.status(job)
    assert record["state"] == "completed"
    assert record["profitability_verified"] is False
    assert record["independent_oos"] is False
    assert record["risk_approved"] is False
    assert record["execution"] == "NONE"
    assert "evidence_sha256" not in record
    assert "parameters" not in record
    assert len(q.audit(job)) == 3


def test_rejects_attempt_to_claim_profitability_or_broker_trade_result(tmp_path):
    q = queue(tmp_path)
    q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    lease = q.claim(worker="worker_1", now=t(2))
    assert lease is not None
    for bad in (
        {**finish_result(), "pnl_usd": 10**12},
        {**finish_result(), "approved_for_live": True},
        {"disposition": "profitable", "reason_code": "passed", "evidence_sha256": HEX64},
        {"disposition": "proposal_recorded", "reason_code": "passed", "evidence_sha256": None},
        {"disposition": "rejected", "reason_code": "../escape", "evidence_sha256": None},
    ):
        with pytest.raises(ValueError):
            q.finish(lease, now=t(3), result=bad)
    assert q.finish(lease, now=t(4), result=finish_result())


def test_rejected_hypothesis_keeps_negative_evidence_without_retries(tmp_path):
    q = queue(tmp_path)
    job = q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    lease = q.claim(worker="worker_1", now=t(2))
    assert q.finish(lease, now=t(3), result={
        "disposition": "rejected", "reason_code": "invalid_hypothesis", "evidence_sha256": None,
    })
    assert q.status(job)["state"] == "rejected"
    assert q.claim(worker="worker_2", now=t(4)) is None
    assert q.audit(job)[-1]["event_type"] == "proposal_rejected"


def test_restart_recovers_private_sqlite_and_avoids_duplicate_submission(tmp_path):
    f = tmp_path / "persistent.sqlite3"
    q = ResearchQueue(f)
    job = q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    lease = q.claim(worker="worker_1", now=t(2), lease_seconds=10)
    del q
    q2 = ResearchQueue(f)
    assert q2.counts()["paused"] is False
    assert q2.submit(hypothesis(agent="forge"), now=t(3)) == job
    assert q2.claim(worker="worker_2", now=t(9), lease_seconds=10) is None
    retry = q2.claim(worker="worker_2", now=t(13), lease_seconds=10)
    assert retry and retry.attempt == 2
    assert retry.token != lease.token
    assert q2.finish(lease, now=t(14), result=finish_result()) is False
    assert q2.finish(retry, now=t(14), result=finish_result()) is True
    assert q2.status(job)["attempts"] == 2
    events = [e["event_type"] for e in q2.audit(job)]
    assert events == [
        "submitted", "claimed", "lease_expired_requeued",
        "claimed", "research_artifact_recorded",
    ]


def test_exactly_three_leases_before_fail_closed_exhaustion(tmp_path):
    q = queue(tmp_path)
    job = q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    for n in range(MAX_ATTEMPTS):
        lease = q.claim(worker=f"worker_{n}", now=t(2+n*20), lease_seconds=10)
        assert lease and lease.attempt == n+1
    assert q.claim(worker="worker_final", now=t(65), lease_seconds=10) is None
    assert q.status(job)["state"] == "exhausted"
    assert q.status(job)["attempts"] == MAX_ATTEMPTS
    assert q.audit(job)[-1]["event_type"] == "lease_expired_exhausted"


def test_heartbeat_extension_and_token_fencing(tmp_path):
    q = queue(tmp_path)
    job = q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    lease = q.claim(worker="worker_1", now=t(2), lease_seconds=10)
    assert q.heartbeat(lease, now=t(8), extend_seconds=30) is True
    assert q.claim(worker="worker_2", now=t(20), lease_seconds=10) is None
    forged = Lease(lease.job_id, lease.attempt, "not-the-original-lease", lease.expires_utc)
    assert q.heartbeat(forged, now=t(20)) is False
    assert q.finish(forged, now=t(20), result=finish_result()) is False
    assert q.finish(lease, now=t(20), result=finish_result()) is True
    assert q.status(job)["state"] == "completed"


def test_operator_pause_revokes_inflight_claim_and_remains_paused_after_restart(tmp_path):
    database = tmp_path / "x.sqlite3"
    q = ResearchQueue(database)
    job = q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    lease = q.claim(worker="worker_1", now=t(2))
    q.set_paused(True, now=t(3))
    assert q.counts()["paused"] is True
    assert q.status(job)["state"] == "queued"
    assert q.finish(lease, now=t(4), result=finish_result()) is False
    restarted = ResearchQueue(database)
    assert restarted.claim(worker="worker_2", now=t(5)) is None
    restarted.set_paused(False, now=t(6))
    new = restarted.claim(worker="worker_2", now=t(7))
    assert new and new.attempt == 2
    assert restarted.finish(lease, now=t(8), result=finish_result()) is False
    assert restarted.finish(new, now=t(8), result=finish_result()) is True
    assert "operator_pause_revoked_lease" in [e["event_type"] for e in restarted.audit(job)]


def test_max_four_concurrent_active_claims(tmp_path):
    q = queue(tmp_path)
    ids = [q.submit(hypothesis(lookback=n), now=t(n)) for n in range(20, 26)]
    q.set_paused(False, now=t(30))
    leases = [q.claim(worker=f"worker_{n}", now=t(31)) for n in range(MAX_ACTIVE)]
    assert all(leases)
    assert len({lease.job_id for lease in leases}) == MAX_ACTIVE
    assert q.claim(worker="worker_overflow", now=t(32)) is None
    assert q.finish(leases[0], now=t(33), result=finish_result()) is True
    next_lease = q.claim(worker="worker_overflow", now=t(34))
    assert next_lease and next_lease.job_id not in {z.job_id for z in leases}
    assert q.counts()["leased"] == MAX_ACTIVE


def test_atomic_submission_rollback_on_journal_error(tmp_path, monkeypatch):
    q = queue(tmp_path)
    before = q.counts()
    original = ResearchQueue._event

    def fail(*args):
        raise RuntimeError("simulated crash between DB row and journal")
    monkeypatch.setattr(ResearchQueue, "_event", staticmethod(fail))
    with pytest.raises(RuntimeError, match="simulated crash"):
        q.submit(hypothesis(), now=t())
    monkeypatch.setattr(ResearchQueue, "_event", staticmethod(original))
    assert q.counts() == before
    job = q.submit(hypothesis(), now=t(1))
    assert len(q.audit(job)) == 1


def test_finish_rollback_preserves_active_claim_when_event_insert_fails(tmp_path, monkeypatch):
    q = queue(tmp_path)
    job = q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    lease = q.claim(worker="worker_1", now=t(2))
    original = ResearchQueue._event

    def fail(*args):
        raise RuntimeError("simulated commit failure")
    monkeypatch.setattr(ResearchQueue, "_event", staticmethod(fail))
    with pytest.raises(RuntimeError, match="simulated commit failure"):
        q.finish(lease, now=t(3), result=finish_result())
    monkeypatch.setattr(ResearchQueue, "_event", staticmethod(original))
    assert q.status(job)["state"] == "leased"
    assert q.finish(lease, now=t(4), result=finish_result())
    assert q.status(job)["state"] == "completed"


def test_concurrent_same_proposal_submissions_across_independent_process_handles(tmp_path):
    path = tmp_path / "shared.sqlite3"
    ResearchQueue(path)

    def task(i):
        return ResearchQueue(path).submit(
            hypothesis(agent="nova" if i % 2 else "forge", campaign=f"campaign-{i}"), now=t(i)
        )
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(task, range(32)))
    assert len(set(ids)) == 1
    q = ResearchQueue(path)
    assert q.counts()["queued"] == 1
    assert len(q.audit(ids[0])) == 1


def test_concurrent_claims_dont_double_allocate_same_job(tmp_path):
    path = tmp_path / "claims.sqlite3"
    q = ResearchQueue(path)
    job = q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))

    def take(i):
        return ResearchQueue(path).claim(worker=f"worker_{i}", now=t(2))
    with ThreadPoolExecutor(max_workers=12) as pool:
        leases = list(pool.map(take, range(12)))
    successful = [x for x in leases if x]
    assert len(successful) == 1
    assert successful[0].job_id == job
    assert ResearchQueue(path).counts()["leased"] == 1


def test_restart_stress_keeps_every_experiment_and_no_duplicate_counts(tmp_path):
    path = tmp_path / "stress.sqlite3"
    q = ResearchQueue(path)
    ids = []
    for i in range(60):
        ids.append(q.submit(hypothesis(lookback=100+i), now=t(i)))
    assert len(set(ids)) == 60
    q.set_paused(False, now=t(100))
    for i in range(60):
        q = ResearchQueue(path)
        lease = q.claim(worker="restart_worker", now=t(101+i))
        assert lease is not None
        assert q.finish(lease, now=t(101+i), result=finish_result())
    q = ResearchQueue(path)
    assert q.counts()["completed"] == 60
    assert q.counts()["queued"] == 0
    assert sum(len(q.audit(job)) for job in ids) == 60*3
    assert all(q.status(job)["risk_approved"] is False for job in ids)


def test_time_and_attempt_bounds_reject_bad_worker_controls(tmp_path):
    q = queue(tmp_path)
    q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    for name in ("../test", "X", "", "worker with space"):
        with pytest.raises(ValueError):
            q.claim(worker=name, now=t(2))
    for bad in (True, 0, 9, 3601, 30.5):
        with pytest.raises(ValueError):
            q.claim(worker="good_worker", now=t(2), lease_seconds=bad)
    with pytest.raises(ValueError, match="aware UTC"):
        q.claim(worker="worker_1", now=datetime(2026, 10, 30))


def test_private_sqlite_refuses_symlink(tmp_path):
    original = tmp_path / "original.sqlite3"
    ResearchQueue(original)
    link = tmp_path / "link.sqlite3"
    try:
        link.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem does not support symlinks")
    with pytest.raises(ValueError, match="real existing parent"):
        ResearchQueue(link)


def test_read_only_status_and_audit_expose_no_strategy_parameters_or_lease_tokens(tmp_path):
    q = queue(tmp_path)
    job = q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    lease = q.claim(worker="worker_1", now=t(2))
    api = json.dumps({"status": q.status(job), "events": q.audit(job)}, sort_keys=True)
    assert lease.token not in api
    assert HEX64 not in api
    assert "lookback" not in api
    assert "parameters" not in api
    assert "evidence_sha256" not in api
    assert "order_send" not in api


def test_reject_future_prospective_even_if_agent_claims_validated(tmp_path):
    q = queue(tmp_path)
    p = hypothesis()
    p["exposure_context"] = "future_prospective"
    with pytest.raises(ValueError):
        q.submit(p, now=t())
    assert q.counts()["queued"] == 0


def test_result_requires_exact_schema_and_no_arbitrary_llm_text(tmp_path):
    q = queue(tmp_path)
    q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    lease = q.claim(worker="worker_1", now=t(2))
    for bad in (
        {"disposition": "proposal_recorded", "evidence_sha256": HEX64},
        {**finish_result(), "commentary": "Trust my alpha"},
        {**finish_result(), "reason_code": "sentinel approved live"},
        {"disposition": "risk_approved", "reason_code": "passed", "evidence_sha256": HEX64},
    ):
        with pytest.raises(ValueError):
            q.finish(lease, now=t(3), result=bad)


def test_external_result_record_is_not_authoritative_execution(tmp_path):
    q = queue(tmp_path)
    job = q.submit(hypothesis(), now=t())
    q.set_paused(False, now=t(1))
    lease = q.claim(worker="worker_1", now=t(2))
    q.finish(lease, now=t(3), result=finish_result())
    with sqlite3.connect(q.path) as db:
        stored = db.execute("SELECT payload,evidence_sha256,state FROM research_jobs WHERE id=?", (job,)).fetchone()
    assert stored[2] == "completed"
    assert stored[1] == "f"*64  # unverified artifact pointer; no fabricated performance
    assert "approved_for_live" not in stored[0]
    assert "net_profit" not in stored[0]


def aql_record():
    # Shape of AI Quant Lab V4 Institutional HypothesisRecord.model_dump(mode="json").
    return {
        "hypothesis_id": "hypothesis_123",
        "campaign_id": "campaign_20261030",
        "proposed_by": "nova",
        "strategy_name": "kalman_adaptive_trend",
        "parameters": {"lookback": 20, "threshold": 0.25},
        "statement": "A price move may persist when a stable latent slope is present.",
        "economic_rationale": "A persistent slope may reflect slow order adaptation.",
        "falsification_criteria": [
            "No persistent out-of-sample predictive advantage",
            "Severe sensitivity to execution-cost assumptions",
            "Instability across predeclared market regimes",
        ],
        "compatible_regimes": ["trending_up"],
        "parameters_locked_before_test": True,
        "created_at": "2026-10-30T00:00:00+00:00",
    }


def aql_context():
    return {
        "asset": "XAUUSD",
        "dataset_sha256": HEX64,
        "engine_commit": HEX40,
        "aiquantlab_commit": "c" * 40,
        "timeframe": "M1",
        "window_start_utc": "2025-01-01T00:00:00Z",
        "window_end_exclusive_utc": "2025-07-01T00:00:00Z",
        "quantity_ounces": 1.0,
        "fee_all_in_per_ounce": 0.4,
        "execution_mode": "m1_conservative",
        "exposure_context": "historical_exposed",
    }


def test_aiquantlab_v4_nova_record_maps_to_a_pinned_unverified_gold_proposal(tmp_path):
    row = aql_record()
    context = aql_context()
    proposal = proposal_from_aiquantlab_hypothesis(row, context)
    assert proposal["schema"] == SCHEMA
    assert proposal["producer"] == EXTERNAL_SOURCE
    assert proposal["agent"] == "nova"
    from hashlib import sha256
    pinned = sha256(("AIQUANTLAB_STRATEGY_V4\\0kalman_adaptive_trend"
                     "\\0" + "c" * 40).encode("ascii")).hexdigest()[:40]
    assert proposal["strategy_id"] == "aql_" + pinned
    assert "rationale" not in str(proposal)
    assert "statement" not in str(proposal)
    assert row["economic_rationale"] not in str(proposal)
    assert proposal["fee_all_in_per_ounce"] == 0.4
    q = queue(tmp_path)
    job = q.submit(proposal, now=t())
    assert q.status(job)["state"] == "queued"
    assert q.status(job)["profitability_verified"] is False
    assert q.counts()["paused"] is True


def test_aiquantlab_strategy_code_sha_is_part_of_candidate_identity():
    hypothesis = aql_record()
    context = aql_context()
    first = proposal_identity(proposal_from_aiquantlab_hypothesis(hypothesis, context))[0]
    context["aiquantlab_commit"] = "d" * 40
    second = proposal_identity(proposal_from_aiquantlab_hypothesis(hypothesis, context))[0]
    assert first != second


def test_qualitative_text_cannot_change_experiment_or_supply_backtest_evidence():
    context = aql_context()
    a = aql_record()
    b = deepcopy(a)
    b["statement"] = "A longer revised explanation of an unchanged historical hypothesis."
    b["economic_rationale"] = "Another prose rationale, without any mathematical difference."
    first = proposal_identity(proposal_from_aiquantlab_hypothesis(a, context))[0]
    second = proposal_identity(proposal_from_aiquantlab_hypothesis(b, context))[0]
    assert first == second


@pytest.mark.parametrize("modifier,error", [
    (lambda row: row.update(proposed_by="sentinel"), "Only Nova"),
    (lambda row: row.update(proposed_by="forge"), "Only Nova"),
    (lambda row: row.update(parameters_locked_before_test=False), "locked"),
    (lambda row: row.update(parameters={"eval": "__import__('os')"}), "Parameters"),
    (lambda row: row.update(parameters={"buy_live": True}), "Parameters"),
    (lambda row: row.update(parameters={"forecast": float("nan")}), "Parameters"),
    (lambda row: row.update(statement="short"), "statement"),
    (lambda row: row.update(falsification_criteria=[]), "falsification_criteria"),
    (lambda row: row.update(compatible_regimes=[]), "compatible_regimes"),
    (lambda row: row.update(created_at="2026-10-30T03:00:00+03:00"), "UTC"),
    (lambda row: row.update(quant_score=99.99), "HypothesisRecord fields"),
    (lambda row: row.update(order_send=True), "HypothesisRecord fields"),
    (lambda row: row.update(password="secret"), "HypothesisRecord fields"),
])
def test_non_authoritative_aiquantlab_hypothesis_is_fail_closed(modifier, error):
    row = aql_record()
    modifier(row)
    with pytest.raises(ValueError, match=error):
        proposal_from_aiquantlab_hypothesis(row, aql_context())


def test_aiquantlab_context_cannot_override_market_or_prospective_claims():
    for changes in (
        {"asset": "EURUSD"}, {"execution_mode": "observed_tick_research"},
        {"exposure_context": "future_prospective"},
        {"fee_all_in_per_ounce": 0.10},
        {"aiquantlab_commit": "mutable-main"},
        {"password": "secret"},
        {"approved_for_live": True},
    ):
        ctx = aql_context()
        ctx.update(changes)
        with pytest.raises(ValueError):
            proposal_from_aiquantlab_hypothesis(aql_record(), ctx)


def test_forge_is_not_mistaken_for_a_nova_hypothesis_record():
    row = aql_record()
    row["proposed_by"] = "forge"
    with pytest.raises(ValueError, match="evolution proposal contract"):
        proposal_from_aiquantlab_hypothesis(row, aql_context())

