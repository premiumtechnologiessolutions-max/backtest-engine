"""Private, read-only offline NoRiskFX Terminal v0.19.1 intake preflight.

Prints a metadata-only proof; never prints quote rows, positions or account scope.
Does not call MT5 or a remote service. No trading or execution side effect.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from norisk_quant.integrations.terminal_ticks import MAX_BYTES, import_terminal_ticks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="Private NoRiskFX Terminal tick-request JSON")
    parser.add_argument("--allow-synthetic", action="store_true",
                        help="Explicitly permit self-labeled synthetic test quotes")
    args = parser.parse_args(argv)
    try:
        if args.snapshot.stat().st_size > MAX_BYTES:
            raise ValueError("Input exceeds the private Terminal snapshot limit")
        result = import_terminal_ticks(args.snapshot.read_bytes(), allow_synthetic=args.allow_synthetic)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Import rejected: {type(exc).__name__}: {exc}\n")
    print(json.dumps(result.evidence, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
