"""B08: private offline snapshot for a FUTURE authenticated Research Terminal UI.

Reads existing private paused/active research queue and optionally original
Gold source manifests plus ONE Terminal read-only tick snapshot. Produces an
owner-only metadata-only JSON view, never a public API or web service.
It NEVER resumes the queue, runs research or issues broker orders.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from norisk_quant.unified_research_platform import UnifiedResearchPlatform, ExistingResearchQueueStatus
from norisk_quant.integrations.terminal_ticks import MAX_BYTES
from scripts.preflight_ai_research_source import _private_json


def _private_regular(path: Path, maximum: int) -> None:
    if (not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= maximum):
        raise ValueError("Only bounded private regular source files are accepted")


def write_private_snapshot(output: Path, payload: dict) -> None:
    """Exclusive owner-only file creation; never overwrite a concurrently-owned path."""
    if os.name != "posix":
        raise ValueError("Private report export requires POSIX owner-only evidence controls")
    root = output.parent
    if (not output.is_absolute() or root.is_symlink() or not root.is_dir()
            or output.is_symlink() or output.exists()):
        raise ValueError("Output must be a new file in existing private directory")
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise ValueError("Operator output folder must be owner-only")
    data = (json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False,
                       separators=(",",":"))+"\n").encode("utf-8")
    if not 0 < len(data) <= 128_000:
        raise ValueError("Refusing oversized private research status snapshot")
    created = False
    fd = None
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd,"wb") as stream:
            fd = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if fd is not None:
            os.close(fd)
        if created and output.is_file() and not output.is_symlink():
            output.unlink()
        raise


def build_operator_snapshot(queue_db: Path, *, source_manifests: list[Path] | None = None,
                            terminal_json: Path | None = None) -> dict:
    """Read only EXISTING local queue and metadata, never auto-initialize it."""
    if os.name != "posix":
        raise ValueError("Only POSIX-private evidence is supported in this initial exporter")
    _private_regular(queue_db,512_000_000)
    if queue_db.stat().st_uid != os.getuid() or queue_db.stat().st_mode & 0o077:
        raise ValueError("Research queue permissions must be owner-only")
    # Queue constructor is idempotent; never claim/finish/auto-resume a job.
    platform = UnifiedResearchPlatform(queue=ExistingResearchQueueStatus(queue_db))
    for path in source_manifests or []:
        _private_regular(path,32_768)
        platform.index_declared_source_manifest(_private_json(path))
    if terminal_json is not None:
        _private_regular(terminal_json, MAX_BYTES)
        platform.observe_terminal_snapshot(terminal_json.read_bytes())
    return platform.operator_snapshot()


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-db",type=Path,required=True)
    parser.add_argument("--source-manifest",type=Path,action="append",default=[])
    parser.add_argument("--terminal-json",type=Path)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        # Prevalidate the destination before reading potentially expensive quotes.
        if args.out.is_symlink() or args.out.exists():
            raise ValueError("Existing output can never be overwritten")
        snapshot=build_operator_snapshot(
            args.queue_db,source_manifests=args.source_manifest,
            terminal_json=args.terminal_json,
        )
        write_private_snapshot(args.out,snapshot)
    except (OSError,ValueError,KeyError,TypeError):
        parser.exit(2,"Private operator status export rejected; no research or trade executed.\n")
    print("Private operator status snapshot created; research and trading unchanged.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
