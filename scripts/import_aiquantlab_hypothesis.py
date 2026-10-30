"""Read-only local AI Quant Lab V4 Nova hypothesis -> canonical research queue.

Inputs: private AI Quant Lab HypothesisRecord.model_dump(mode='json') file
and separately verified, operator-supplied canonical XAUUSD research context.
NO broker access, order execution, market fetching or AI-generated P/L.
Queue starts PAUSED and must be resumed explicitly by an operator in
the separate research control plane.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from norisk_quant.research_control_plane import (
    ResearchQueue, proposal_from_aiquantlab_hypothesis,
)

MAX_HYPOTHESIS_BYTES = 16_384
MAX_CONTEXT_BYTES = 8_192


def _read_json(path: Path, maximum: int) -> dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= maximum:
        raise ValueError("A private regular JSON file within the size limit is required")
    def unique_keys(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError("Duplicate key in private research input")
            output[key] = value
        return output
    def fail_nonfinite(value):
        raise ValueError("Nonfinite input is forbidden")
    def finite_float(value):
        num = float(value)
        if not math.isfinite(num):
            raise ValueError("Nonfinite numeric input is forbidden")
        return num
    try:
        obj = json.loads(path.read_text(encoding="utf-8"),
                         object_pairs_hook=unique_keys,
                         parse_constant=fail_nonfinite,
                         parse_float=finite_float)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed private JSON file") from exc
    if type(obj) is not dict:
        raise ValueError("Expected one canonical JSON object")
    return obj


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hypothesis", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--queue-db", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        record = _read_json(args.hypothesis, MAX_HYPOTHESIS_BYTES)
        context = _read_json(args.context, MAX_CONTEXT_BYTES)
        proposal = proposal_from_aiquantlab_hypothesis(record, context)
        queue = ResearchQueue(args.queue_db)
        identifier = queue.submit(proposal, now=now or datetime.now(timezone.utc))
        status = queue.status(identifier)
    except (OSError, ValueError, KeyError) as exc:
        # Never print exception text: malformed user fields may contain secrets.
        parser.exit(2, "Untrusted research intake rejected; no task accepted.\n")
    print(json.dumps({
        "experiment_id": identifier, "state": status["state"],
        "source_agent": status["source_agent"],
        "paused": queue.counts()["paused"],
        "execution": "NONE",
        "source_authentication": "NOT_VERIFIED",
        "independent_oos": False, "risk_approved": False,
        "profitability_verified": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
