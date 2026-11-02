"""Synthetic host-health watchdog tests; no market claims."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from scripts import research_unattended_healthcheck as h


@pytest.fixture
def root(tmp_path):
    return tmp_path


def write(root, state="RESEARCH_RUNNING", *, delta=0, **updates):
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    data = {
        "schema": h.HEALTH_SCHEMA, "status": state,
        "training_only": True, "independent_oos_proven": False,
        "market_edge_confirmed": False, "live_trading_authorized": False,
        "worker_pid": 42 if state == "RESEARCH_RUNNING" else None,
        "verified_generations_reported": 3,
        "supervised_worker_runs": 1,
        "updated_utc": (now + timedelta(seconds=delta)).isoformat(),
    }
    data.update(updates)
    (root / "unattended_research_health.json").write_text(json.dumps(data))
    if state == "TRAINING_CAP_REACHED_NOT_OOS":
        (root / "autonomous_research_status.json").write_text(json.dumps({
            "schema": h.DIR_SCHEMA,
            "status": "COMPLETE_HISTORICAL_TRAINING_ONLY_NOT_OOS",
            "verified_generations": data["verified_generations_reported"],
            "training_only": True, "independent_oos_proven": False,
            "live_trading_authorized": False,
        }))
    return now


@pytest.mark.parametrize("state,expected", [
    ("RESEARCH_RUNNING", 0), ("SLEEPING_BEFORE_SAFE_RESUME", 2),
    ("TRAINING_CAP_REACHED_NOT_OOS", 0),
    ("PAUSED_DISK_BUDGET", 2),
    ("PAUSED_UNATTENDED_RETRY_BUDGET", 2),
    ("FAULT_REQUIRES_EVIDENCE_REVIEW", 2),
    ("UNKNOWN", 3),
])
def test_lifecycle(root, state, expected):
    now = write(root, state)
    code, _ = h.evaluate(root, now=now)
    assert code == expected


def test_missing_and_stale(root):
    assert h.evaluate(root)[0] == 3
    now = write(root, delta=-301)
    assert h.evaluate(root, now=now)[0] == 3
    now = write(root, delta=61)
    assert h.evaluate(root, now=now)[0] == 3


@pytest.mark.parametrize("update", [
    {"independent_oos_proven": True},
    {"live_trading_authorized": True},
    {"market_edge_confirmed": True},
    {"training_only": False},
    {"worker_pid": 0},
    {"updated_utc": "2026-11-02T12:00:00"},
    {"schema": "UNRECOGNIZED"},
])
def test_false_or_corrupt_health_rejected(root, update):
    now = write(root, **update)
    assert h.evaluate(root, now=now)[0] == 3


def test_complete_is_not_out_of_sample(root):
    now = write(root, "TRAINING_CAP_REACHED_NOT_OOS")
    code, result = h.evaluate(root, now=now)
    assert code == 0
    assert "not proven" in result["note"]


def test_symlink_status_rejected(root):
    real = root / "outside.json"
    real.write_text("{}")
    (root / "unattended_research_health.json").symlink_to(real)
    assert h.evaluate(root)[0] == 3


def test_completed_health_remains_durable_after_heartbeat_age(root):
    now = write(root, "TRAINING_CAP_REACHED_NOT_OOS", delta=-86400)
    assert h.evaluate(root, now=now)[0] == 0

@pytest.mark.parametrize("update", [
    {"verified_generations_reported": -1},
    {"verified_generations_reported": True},
    {"supervised_worker_runs": 0},
    {"supervised_worker_runs": "1"},
])
def test_malformed_supervised_counters_rejected(root, update):
    now = write(root, **update)
    assert h.evaluate(root, now=now)[0] == 3


def test_forged_completion_without_verified_generations_rejected(root):
    now = write(root, "TRAINING_CAP_REACHED_NOT_OOS",
                verified_generations_reported=0)
    assert h.evaluate(root, now=now)[0] == 3


def test_missing_director_completion_rejected(root):
    now = write(root, "TRAINING_CAP_REACHED_NOT_OOS")
    (root / "autonomous_research_status.json").unlink()
    assert h.evaluate(root, now=now)[0] == 3


def test_mismatched_director_completion_rejected(root):
    now = write(root, "TRAINING_CAP_REACHED_NOT_OOS")
    path = root / "autonomous_research_status.json"
    evidence = json.loads(path.read_text())
    evidence["verified_generations"] = 2
    path.write_text(json.dumps(evidence))
    assert h.evaluate(root, now=now)[0] == 3


def test_forged_director_oos_rejected(root):
    now = write(root, "TRAINING_CAP_REACHED_NOT_OOS")
    path = root / "autonomous_research_status.json"
    evidence = json.loads(path.read_text())
    evidence["independent_oos_proven"] = True
    path.write_text(json.dumps(evidence))
    assert h.evaluate(root, now=now)[0] == 3


@pytest.mark.parametrize("state", [
    "TRAINING_CAP_REACHED_NOT_OOS",
    "PAUSED_DISK_BUDGET",
    "FAULT_REQUIRES_EVIDENCE_REVIEW",
])
def test_terminal_state_cannot_claim_running_child(root, state):
    now = write(root, state, worker_pid=8765)
    code, report = h.evaluate(root, now=now)
    assert code == 3
    assert report["state"] == "INVALID_HEALTH_EVIDENCE"


@pytest.mark.parametrize("delta,retry,maximum,expected,state", [
    (-120, 900, 300, 2, "SLEEPING_BEFORE_SAFE_RESUME"),
    (-1199, 900, 300, 2, "SLEEPING_BEFORE_SAFE_RESUME"),
    (-1201, 900, 300, 3, "STALE_RETRY_SLEEP"),
    (-1201, None, 300, 2, "SLEEPING_BEFORE_SAFE_RESUME"),
])
def test_retry_sleep_deadline_is_distinct_from_live_heartbeat(
        root, delta, retry, maximum, expected, state):
    now = write(root, "SLEEPING_BEFORE_SAFE_RESUME", delta=delta)
    code, report = h.evaluate(root, now=now, max_age_seconds=maximum,
                              retry_seconds=retry)
    assert code == expected
    assert report["state"] == state


@pytest.mark.parametrize("retry", [0, -1, True, 1.5, "900"])
def test_invalid_retry_deadline_rejected(root, retry):
    with pytest.raises(ValueError, match="retry_seconds"):
        h.evaluate(root, retry_seconds=retry)


def test_naive_reference_clock_is_invalid_evidence(root):
    write(root)
    code, report = h.evaluate(root, now=datetime(2026, 11, 2, 12, 0))
    assert code == 3
    assert report["state"] == "INVALID_HEALTH_EVIDENCE"


def test_forged_director_market_edge_claim_rejected(root):
    now = write(root, "TRAINING_CAP_REACHED_NOT_OOS")
    path = root / "autonomous_research_status.json"
    evidence = json.loads(path.read_text())
    evidence["market_edge_confirmed"] = True
    path.write_text(json.dumps(evidence))
    code, report = h.evaluate(root, now=now)
    assert code == 3
    assert report["state"] == "INVALID_HEALTH_EVIDENCE"
