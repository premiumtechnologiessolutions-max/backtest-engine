"""Synthetic-only tests: preregistration is not a performance certificate."""
from copy import deepcopy

import pytest

from norisk_quant.preregistration import (
    SCHEMA, authorize_future_evaluation, freeze_plan, verify_freeze,
)


def plan():
    return {
        "schema": SCHEMA,
        "strategy": "sweep_reclaim_m1_frozen",
        "strategy_blob_sha": "a" * 40,
        "training_archive_sha256": "b" * 64,
        "registered_at_utc": "2026-10-30T00:00:00Z",
        "known_exposed_through": "2026-10-30",
        "train_end": "2026-10-29",
        "holdout_start": "2026-11-02",
        "holdout_end": "2027-01-29",
        "fee_usd_per_oz": 0.40,
        "parameters": {
            "lookback": 20, "min_excess_usd": .15,
            "reclaim_usd": .05, "stop_buffer_usd": .10,
            "reward_risk": 1.5, "max_stop_usd": 20.0,
        },
        "evidence_status": "FUTURE_UNOBSERVED_NOT_VALIDATED",
    }


def test_frozen_plan_is_deterministic_and_canonical():
    a = freeze_plan(plan())
    b = plan()
    b["parameters"] = dict(reversed(list(b["parameters"].items())))
    assert a == freeze_plan(b)
    assert len(a["sha256"]) == 64
    assert verify_freeze(a) == plan()


def test_future_authorization_requires_external_git_timestamp_and_exact_code():
    envelope = freeze_plan(plan())
    assert authorize_future_evaluation(
        envelope, strategy_blob_sha="a" * 40,
        observed_start="2026-11-02", observed_end="2026-11-30",
        verified_external_commit_before="2026-10-30T01:00:00Z",
    ) == plan()


@pytest.mark.parametrize("field,value", [
    ("holdout_start", "2026-10-30"),
    ("holdout_start", "2026-10-29"),
    ("holdout_end", "2026-11-01"),
    ("train_end", "2026-11-02"),
    ("known_exposed_through", "2026-11-02"),
    ("registered_at_utc", "2026-11-02T00:00:00Z"),
    ("registered_at_utc", "2026-10-30T00:00:00+02:00"),
    ("registered_at_utc", "2026-10-30T00:00Z"),
    ("fee_usd_per_oz", .400001),
    ("fee_usd_per_oz", True),
    ("strategy_blob_sha", "Z" * 40),
    ("training_archive_sha256", "b" * 63),
    ("evidence_status", "PROFITABLE"),
    ("strategy", "../../escape"),
    ("holdout_end", "2027-02-30"),
])
def test_bad_preregistration_fails_closed(field, value):
    p = plan()
    p[field] = value
    with pytest.raises(ValueError):
        freeze_plan(p)


@pytest.mark.parametrize("value", [
    {"stop_usd": float("nan")},
    {"stop_usd": float("inf")},
    {"stop_usd": True},
    {"stop_usd": None},
    {"stop_usd": [1, 2]},
    {"stop_usd": {"nested": 1}},
    {"rr": 1.5},
    {},
])
def test_noncanonical_parameters_rejected(value):
    p = plan()
    p["parameters"] = value
    with pytest.raises(ValueError):
        freeze_plan(p)


def test_mutated_frozen_plan_and_digest_fail():
    envelope = freeze_plan(plan())
    altered = deepcopy(envelope)
    altered["plan"]["parameters"]["lookback"] = 40
    with pytest.raises(ValueError, match="changed"):
        verify_freeze(altered)
    altered = deepcopy(envelope)
    altered["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="changed"):
        verify_freeze(altered)


@pytest.mark.parametrize("external,code,start,end", [
    ("2026-11-02T00:00:00Z", "a" * 40, "2026-11-02", "2026-11-30"),
    ("2026-10-29T23:59:59Z", "a" * 40, "2026-11-02", "2026-11-30"),
    ("2026-10-30T01:00:00Z", "c" * 40, "2026-11-02", "2026-11-30"),
    ("2026-10-30T01:00:00Z", "a" * 40, "2026-10-30", "2026-11-30"),
    ("2026-10-30T01:00:00Z", "a" * 40, "2026-11-02", "2027-02-01"),
    ("2026-10-30T01:00:00Z", "a" * 40, "2026-12-01", "2026-11-30"),
])
def test_authorization_rejects_late_freeze_modified_code_or_out_of_window(
    external, code, start, end,
):
    with pytest.raises(ValueError):
        authorize_future_evaluation(
            freeze_plan(plan()), strategy_blob_sha=code,
            observed_start=start, observed_end=end,
            verified_external_commit_before=external,
        )


def test_extra_schema_fields_fail_closed():
    p = plan()
    p["claim_monthly_profit"] = True
    with pytest.raises(ValueError):
        freeze_plan(p)
