"""Synthetic lock tests; never touch private quotes or execute backtests."""
from datetime import datetime, timezone
import os

import pytest
from scripts import research_job_month_lease as lease

FINGERPRINT = "a" * 64
NOW = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _plan():
    return {
        "request_fingerprint": FINGERPRINT,
        "status": "PLANNED_ONLY_NOT_EXECUTED",
        "backtests_executed": 0,
        "source_verified_months": 0,
        "slots": [{"month": "2026-11", "start_utc": "2026-11-01",
                   "end_exclusive_utc": "2026-12-01", "slot_fingerprint": "b" * 64},
                  {"month": "2026-12", "start_utc": "2026-12-01",
                   "end_exclusive_utc": "2027-01-01", "slot_fingerprint": "c" * 64}],
    }


def _setup(monkeypatch):
    monkeypatch.setattr(lease, "verify_plan", lambda root, fp: _plan())


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only flock contract")
def test_exclusive_lock_and_release(tmp_path, monkeypatch):
    _setup(monkeypatch)
    with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW) as receipt:
        assert receipt["status"] == "RESERVED_ONLY_NO_BACKTEST"
        assert receipt["backtests_executed"] == 0
        assert receipt["source_verified"] is False
        assert receipt["monthly_pnl_usd_per_oz"] is None
        with pytest.raises(ValueError, match="already reserved"):
            with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
                pass
        with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-12", now_utc=NOW):
            pass
    with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
        pass
    directory = tmp_path / "reports" / "research_job_locks"
    assert len(list(directory.iterdir())) == 2
    assert all(p.stat().st_size == 0 for p in directory.iterdir())
    assert directory.stat().st_mode & 0o077 == 0
    assert all(p.stat().st_mode & 0o077 == 0 for p in directory.iterdir())


@pytest.mark.parametrize("fp,month", [(FINGERPRINT[:-1], "2026-11"),
                                      (FINGERPRINT, "2026-13"),
                                      (FINGERPRINT, "../2026-11"),
                                      (None, "2026-11")])
def test_invalid_identifiers_fail_before_io(tmp_path, monkeypatch, fp, month):
    _setup(monkeypatch)
    with pytest.raises(ValueError):
        with lease.reserve_closed_month(tmp_path, fp, month, now_utc=NOW):
            pass
    assert not (tmp_path / "reports").exists()


def test_future_month_fails_before_io(tmp_path, monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError, match="not closed"):
        with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-12",
                                        now_utc=datetime(2026, 12, 31, tzinfo=timezone.utc)):
            pass
    assert not (tmp_path / "reports").exists()


def test_unplanned_month_fails_before_io(tmp_path, monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError, match="not present"):
        with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-10", now_utc=NOW):
            pass
    assert not (tmp_path / "reports").exists()


def test_preflight_drift_after_lock_fails_closed(tmp_path, monkeypatch):
    calls = [0]
    def changing(root, fp):
        calls[0] += 1
        plan = _plan()
        if calls[0] == 2:
            plan["slots"][0]["slot_fingerprint"] = "d" * 64
        return plan
    monkeypatch.setattr(lease, "verify_plan", changing)
    with pytest.raises(ValueError, match="changed"):
        with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
            pass
    assert calls[0] == 2
    _setup(monkeypatch)
    with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
        pass


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_world_readable_lock_rejected(tmp_path, monkeypatch):
    _setup(monkeypatch)
    with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
        pass
    path = tmp_path / "reports" / "research_job_locks" / (FINGERPRINT + ".2026-11.lock")
    path.chmod(0o644)
    with pytest.raises(ValueError, match="Unsafe"):
        with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
            pass


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_symlinked_lock_rejected(tmp_path, monkeypatch):
    _setup(monkeypatch)
    with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
        pass
    path = tmp_path / "reports" / "research_job_locks" / (FINGERPRINT + ".2026-11.lock")
    backup = path.with_suffix(".bak")
    path.rename(backup)
    path.symlink_to(backup)
    with pytest.raises((OSError, ValueError)):
        with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
            pass


def test_snapshot_rejection_prevents_lock_creation(tmp_path, monkeypatch):
    def fail(*args):
        raise ValueError("Frozen checkout mismatch")
    monkeypatch.setattr(lease, "verify_plan", fail)
    with pytest.raises(ValueError, match="checkout"):
        with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
            pass
    assert not (tmp_path / "reports").exists()


def test_utc_clock_required(tmp_path, monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError, match="UTC-aware"):
        with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11",
                                        now_utc=datetime(2027, 1, 1)):
            pass


def test_nonempty_lock_file_rejected(tmp_path, monkeypatch):
    _setup(monkeypatch)
    with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
        pass
    path = tmp_path / "reports" / "research_job_locks" / (FINGERPRINT + ".2026-11.lock")
    path.write_text("fake completed")
    with pytest.raises(ValueError, match="Unsafe"):
        with lease.reserve_closed_month(tmp_path, FINGERPRINT, "2026-11", now_utc=NOW):
            pass
