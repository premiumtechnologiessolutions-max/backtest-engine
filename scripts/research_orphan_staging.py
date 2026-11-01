"""Quarantine interrupted private arithmetic replay staging directories.

Call only while holding the enclosing research batch lock. The canonical
replay executor already stages and atomically publishes completed shards.
A force-killed process may leave hidden staging. Never mistake that for
verified evidence: move it to owner-only retention instead of deleting it.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

GENERATION = re.compile(r"generation_[0-9]{4}\Z")
STAGING = re.compile(r"\.nrfx_arithmetic_training_[a-zA-Z0-9_-]+\Z")
QUARANTINE = ".quarantined_training_staging"


def quarantine_abandoned_staging_locked(root: Path, *, max_orphans: int = 32) -> list[str]:
    """Retain partial staging; leave complete validated shards untouched.

    Caller MUST hold exclusive_batch_lock(root). Symlinks, nonregular nodes,
    collisions and a large orphan count are refused before any move.
    Quarantined files are NOT audited market results and may be large.
    """
    root = Path(root)
    if (root.is_symlink() or not root.is_dir() or type(max_orphans) is not int
            or not 1 <= max_orphans <= 1024):
        raise ValueError("Unsafe orphan-recovery root or budget")
    orphaned: list[tuple[str, Path]] = []
    for folder in sorted(root.iterdir()):
        if GENERATION.fullmatch(folder.name) is None:
            continue
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Unsafe research generation directory")
        for stage in sorted(folder.iterdir()):
            if not stage.name.startswith(".nrfx_arithmetic_training_"):
                continue
            if STAGING.fullmatch(stage.name) is None or stage.is_symlink() or not stage.is_dir():
                raise ValueError("Unsafe interrupted arithmetic replay staging")
            for node in stage.rglob("*"):
                if node.is_symlink() or not (node.is_dir() or node.is_file()):
                    raise ValueError("Interrupted replay contains symlink/nonregular evidence")
            orphaned.append((f"{folder.name}__{stage.name}", stage))
    if len(orphaned) > max_orphans:
        raise ValueError("Exceeded bounded interrupted replay retention budget")
    if not orphaned:
        return []
    target_root = root / QUARANTINE
    if target_root.is_symlink() or (target_root.exists() and not target_root.is_dir()):
        raise ValueError("Unsafe quarantined research evidence destination")
    for name, _ in orphaned:
        target = target_root / name
        if target.exists() or target.is_symlink():
            raise FileExistsError("Interrupted research evidence already quarantined")
    target_root.mkdir(mode=0o700, exist_ok=True)
    info = target_root.stat()
    if (os.name == "posix"
            and (info.st_uid != os.getuid() or info.st_mode & 0o077)):
        raise ValueError("Quarantine directory must be owner-only (0700)")
    names = []
    for name, stage in orphaned:
        os.rename(stage, target_root / name)
        names.append(name)
    return names
