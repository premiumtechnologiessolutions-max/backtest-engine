"""Print construction-only quant mission-control JSON, no execution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from norisk_quant.construction_mission_control import construction_snapshot

_MAX_BYTES = 32 * 1024 * 1024


def _read_frozen(path: Path) -> dict:
    path = Path(path)
    if (path.is_symlink() or not path.is_file()
            or path.suffix.lower() != ".json"
            or path.stat().st_size > _MAX_BYTES):
        raise ValueError("Unsafe or oversized quant design JSON")
    def pairs_hook(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate construction JSON key")
            result[key] = value
        return result
    def no_nan(value):
        raise ValueError("Nonfinite construction JSON")
    design = json.loads(path.read_text(encoding="utf-8"),
                        object_pairs_hook=pairs_hook, parse_constant=no_nan)
    if type(design) is not dict:
        raise ValueError("Quant design must be an object")
    return design


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--now-ms", type=int)
    args = parser.parse_args(argv)
    output = construction_snapshot(
        _read_frozen(args.design),
        database=args.database, now_ms=args.now_ms,
        backup_snapshot_dir=args.backup_dir)
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
