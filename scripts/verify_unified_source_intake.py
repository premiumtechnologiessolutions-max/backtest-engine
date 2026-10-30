"""Offline read-only NoRiskFX Terminal -> Unified Data Hub private preflight."""
from __future__ import annotations

import argparse
import json

from norisk_quant.integrations.unified_source_intake import inspect_local_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_terminal_json", help="Local original read-only Terminal tick request JSON")
    parser.add_argument("--allow-synthetic", action="store_true", help="Explicitly accept test-only synthetic feed")
    args = parser.parse_args(argv)
    try:
        result = inspect_local_file(
            args.private_terminal_json,
            allow_synthetic=args.allow_synthetic,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Data Hub preflight rejected: {type(exc).__name__}\n")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
