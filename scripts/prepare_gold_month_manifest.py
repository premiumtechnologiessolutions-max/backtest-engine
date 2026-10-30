"""Operator-only one-time private Gold M1 month manifest preparation.

Example:
 python scripts/prepare_gold_month_manifest.py --source LOCAL_GOLD.zip \
   --year 2012 --month 1 --out PRIVATE_DIR/2012-01-manifest.json

The output is a LOCAL CANDIDATE, not prospective scientific preregistration.
Create BEFORE strategy execution and record a separately reviewed digest.
No file overwrite, no Oracle, MT5, broker calls or market-price printing.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from norisk_quant.month_source_manifest import build_month_source_candidate


def write_new_private_manifest(path: Path, manifest: dict) -> None:
    """Exclusive-create and fsync. Never remove a concurrently owned file."""
    if os.name != "posix":
        raise ValueError("Private manifest creation requires reviewed POSIX file permissions")
    if not path.is_absolute() or path.is_symlink() or path.exists() or not path.parent.is_dir():
        raise ValueError("Manifest destination must be a new private absolute file")
    if path.parent.is_symlink() or (path.parent.stat().st_mode & 0o077):
        raise ValueError("Private manifest parent directory must be owner-only")
    data = (json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                       allow_nan=False, ensure_ascii=False) + "\n").encode("utf-8")
    if not 0 < len(data) <= 8192:
        raise ValueError("Unexpected oversized source manifest")
    fd = None
    created = False
    try:
        fd = os.open(path, os.O_EXCL | os.O_CREAT | os.O_WRONLY, 0o600)
        created = True
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if fd is not None:
            os.close(fd)
        if created and path.is_file() and not path.is_symlink():
            path.unlink()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # Do not even run lengthy source inspection if output exists:
        # changing an already-frozen scientific source candidate is forbidden.
        if args.out.exists() or args.out.is_symlink():
            raise ValueError("Existing manifest cannot be replaced")
        result = build_month_source_candidate(args.source, args.year, args.month)
        write_new_private_manifest(args.out, result.manifest)
    except (OSError, ValueError, TypeError, OverflowError):
        # A malformed archive, directory or user-controlled path may contain
        # sensitive account info: do not echo it in the error message.
        parser.exit(2, "Original Gold M1 month source not prepared; no research executed.\n")
    print(json.dumps(result.public_status(), sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
