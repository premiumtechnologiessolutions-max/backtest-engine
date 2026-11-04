"""Operator-only metadata backup CLI, never auto-run or auto-restore."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from scripts.durable_backup_attestation import (
    backup_durable_state, verify_durable_backup, restore_durable_backup,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    create = sub.add_parser("backup")
    create.add_argument("--database", type=Path, required=True)
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--id", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--snapshot-dir", type=Path, required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("--snapshot-dir", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.operation == "backup":
        result = backup_durable_state(args.database, args.root, args.id)
    elif args.operation == "verify":
        result = verify_durable_backup(args.snapshot_dir)
    else:
        result = restore_durable_backup(args.snapshot_dir, args.destination)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
