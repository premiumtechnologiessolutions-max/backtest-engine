"""Synthetic /proc fixtures only: no OS processes or research workers launched."""
from pathlib import Path

import pytest

from scripts.durable_worker_process_supervisor import (
    LinuxProcInspector, ProcessIdentity,
)

BOOT = "11111111-2222-3333-4444-555555555555"
OTHER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def proc_stat(pid: int, group: int, ticks: int, state="S"):
    # Field 3 is state; field 5 is process group; field 22 start ticks.
    fields = [state, "1", str(group)] + ["0"] * 16 + [str(ticks)]
    return f"{pid} (worker (synthetic) name) " + " ".join(fields)


def fixture(tmp_path: Path):
    root = tmp_path / "proc"
    (root / "sys/kernel/random").mkdir(parents=True)
    (root / "sys/kernel/random/boot_id").write_text(BOOT)
    return root, LinuxProcInspector(root)


def write_proc(root: Path, pid: int, group: int, ticks: int, state="S"):
    folder = root / str(pid)
    folder.mkdir(exist_ok=True)
    (folder / "stat").write_text(proc_stat(pid, group, ticks, state))


def test_live_group_member_blocks_exit_after_leader_disappears(tmp_path):
    root, inspector = fixture(tmp_path)
    write_proc(root, 5001, 5001, 100)
    identity = inspector.capture(5001)
    write_proc(root, 5002, 5001, 101)
    (root / "5001/stat").unlink()
    (root / "5001").rmdir()
    assert inspector.observe_exit(identity) == "ACTIVE"
    (root / "5002/stat").write_text(proc_stat(5002, 5001, 101, "Z"))
    assert inspector.observe_exit(identity) == "EXITED_SAME_BOOT_NO_GROUP_MEMBERS"


def test_pid_reuse_without_original_group_is_not_original_process(tmp_path):
    root, inspector = fixture(tmp_path)
    write_proc(root, 5001, 5001, 100)
    identity = inspector.capture(5001)
    # The old process is gone, PID reused with another start time/group.
    (root / "5001/stat").write_text(proc_stat(5001, 5001, 200, "Z"))
    assert inspector.observe_exit(identity) == "EXITED_SAME_BOOT_NO_GROUP_MEMBERS"
    (root / "5001/stat").write_text(proc_stat(5001, 5001, 200, "S"))
    # Same numeric process group ID may have been recycled; fail closed.
    assert inspector.observe_exit(identity) == "ACTIVE"


def test_boot_change_never_proves_exit(tmp_path):
    root, inspector = fixture(tmp_path)
    write_proc(root, 5001, 5001, 100)
    identity = inspector.capture(5001)
    (root / "sys/kernel/random/boot_id").write_text(OTHER)
    (root / "5001/stat").unlink()
    assert inspector.observe_exit(identity) == "UNKNOWN_BOOT_CHANGED"


def test_unreadable_proc_member_never_proves_exit(tmp_path):
    root, inspector = fixture(tmp_path)
    write_proc(root, 5001, 5001, 100)
    identity = inspector.capture(5001)
    (root / "5001/stat").write_text("malformed stat")
    assert inspector.observe_exit(identity) == "UNKNOWN_PROC_STATUS"


def test_capture_rejects_zombie_and_nonleader(tmp_path):
    root, inspector = fixture(tmp_path)
    write_proc(root, 5001, 5001, 100, "Z")
    with pytest.raises(ValueError, match="live isolated"):
        inspector.capture(5001)
    (root / "5001/stat").write_text(proc_stat(5001, 4999, 100))
    with pytest.raises(ValueError, match="live isolated"):
        inspector.capture(5001)


def test_boot_id_invalid_is_fail_closed(tmp_path):
    root, inspector = fixture(tmp_path)
    (root / "sys/kernel/random/boot_id").write_text("not-a-uuid")
    with pytest.raises(ValueError, match="boot identifier"):
        inspector.boot()
