"""Private offline No Risk FX canonical research worker — one job per invocation.

Default: status only. --resume / --pause control local research-only queue.
--execute explicitly permits ONE frozen, audited HISTORICAL M1 simulation
when unpaused. No MT5, Oracle, internet, orders or autonomous daemon.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from norisk_quant.research_control_plane import ResearchQueue
from norisk_quant.canonical_research_worker import execute_one_approved_job
from scripts.preflight_ai_research_source import _private_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-db", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--resume", action="store_true")
    modes.add_argument("--pause", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--original-gold-zip", type=Path)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--private-output", type=Path)
    args = parser.parse_args(argv)

    try:
        queue = ResearchQueue(args.queue_db)
        if args.resume or args.pause:
            queue.set_paused(args.pause, now=datetime.now(timezone.utc))
            result = {"paused": queue.counts()["paused"],
                      "execution": "NONE_OPERATOR_CONTROL"}
        elif args.execute:
            if not all((
                args.source_manifest, args.original_gold_zip,
                args.checkout, args.private_output,
            )):
                raise ValueError("Private original source, immutable manifest, exact checkout and output required")
            evidence = _private_json(args.source_manifest)
            result = execute_one_approved_job(
                queue, source_manifest=evidence, data_zip=args.original_gold_zip,
                checkout=args.checkout, output_root=args.private_output,
            )
        else:
            # Keep status output compact and non-sensitive: no job payload.
            result = {"counts": queue.counts(), "execution": "NONE_STATUS_ONLY"}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        # Never echo source data, local path, broker identity or AI text.
        parser.exit(2, "Private research worker rejected or failed audit; inspect protected local evidence.\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
