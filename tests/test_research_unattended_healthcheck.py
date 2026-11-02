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
        "worker_pid": 42,
        "updated_utc": (now + timedelta(seconds=delta)).isoformat(),
    }
    data.update(updates)
    (root / "unattended_research_health.json").write_text(json.dumps(data))
    return now


@pytest.mark.parametrize("state,expected", [
    ("RESEARCH_RUNNING", 0), ("SLEEPING_BEFORE_SAFE_RESUME", 0),
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
