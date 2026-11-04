"""Offline construction DAG registration and audit CLI. NO WORKER EXECUTION."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.durable_research_state import DurableResearchState
from scripts.durable_inert_campaign_registry import (
    register_inert_campaign, audit_inert_registry,
)
from scripts.durable_operations_gate import evaluate
from scripts.quant_construction_snapshot import _read_frozen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("register")
    create.add_argument("--design", type=Path, required=True)
    create.add_argument("--database", type=Path, required=True)
    check = sub.add_parser("audit")
    check.add_argument("--database", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "register":
        # Constructing the registry cannot dispatch research, even if the
        # database contains old external receipts or active worker metadata.
        store = DurableResearchState(args.database)
        result = register_inert_campaign(store, _read_frozen(args.design))
    else:
        # Never initialize a missing DB merely because an auditor inspected it.
        code, report = evaluate(args.database)
        if code == 3:
            raise ValueError("Durable construction registry is missing or invalid")
        result = {
            "schema": "NRFX_CONSTRUCTION_REGISTRY_CLI_V1",
            "registry": report["construction_registry"],
            "control_plane_health": report["status"],
            "market_data_accessed": False,
            "workers_started": False,
            "research_result_accepted": False,
        }
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
