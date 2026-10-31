"""Atomic, private offline HTML export for audited research metadata.

Never publishes local queue identifiers or research data to a web service.
This is a filesystem safety boundary, not a multi-user sandbox.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile


def write_private_html(destination: Path, html: str) -> None:
    """Replace an HTML export atomically with owner-only permissions on POSIX.

    Reject symlinked path components and pre-existing linked/nonregular targets.
    On failure, preserve any prior valid export and remove the temporary file.
    """
    if not isinstance(destination, Path) or destination.suffix.lower() != ".html":
        raise ValueError("Research Terminal export requires a .html destination")
    if type(html) is not str:
        raise ValueError("Research Terminal HTML must be text")
    parent = destination.absolute().parent
    for part in (parent, *parent.parents):
        if part.is_symlink():
            raise ValueError("Refusing symlinked export parent")
    parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("Refusing symlinked export destination")
    if destination.exists():
        info = destination.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Refusing nonregular or hardlinked export destination")
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=".nrfx-terminal-", suffix=".tmp", dir=parent)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            if os.name == "posix":
                os.fchmod(stream.fileno(), 0o600)
            stream.write(html)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, destination)
        tmp_name = None
        if os.name == "posix" and hasattr(os, "O_DIRECTORY"):
            dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if tmp_name is not None:
            Path(tmp_name).unlink(missing_ok=True)
