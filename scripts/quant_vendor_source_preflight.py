"""Read-only frozen Quant campaign vendor-source preflight.

Compares materialized vendor gitlinks to the actual frozen campaign commit.
No engine, backtest, provider, Python strategy, ZIP or research worker runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from norisk_quant.campaign_sharding import verify_sharded_campaign
from norisk_quant.vendor_checkout_attestation import attest_pinned_vendor_checkout
from scripts.quant_construction_snapshot import _read_frozen

SCHEMA = "NRFX_FROZEN_VENDOR_SOURCE_PREFLIGHT_V1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def preflight_vendor_sources(frozen_campaign: dict, checkout_root: Path) -> dict:
    """Check every planned external simulator, without cherry-picking one."""
    design = verify_sharded_campaign(frozen_campaign)
    spec = design["normalized_global_spec"]
    parent_sha = spec["source_commit"]
    required = sorted(set(spec["execution_engines"]) - {"norisk_quant"})
    verified = []
    blocked = []
    for engine in required:
        try:
            proof = attest_pinned_vendor_checkout(Path(checkout_root), engine)
            if proof["parent_commit"] != parent_sha:
                raise ValueError("Vendor source checkout not from frozen campaign parent")
            verified.append({
                "engine": engine,
                "gitlink_commit": proof["gitlink_commit"],
                "parent_commit": proof["parent_commit"],
                "selected_entrypoints": proof["selected_entrypoints"],
                "status": "LOCAL_SOURCE_CHECKED_NOT_EXECUTED",
            })
        except (OSError, TypeError, ValueError):
            # Do not publish local filesystem paths or Git stderr.
            blocked.append(engine)
    body = {
        "schema": SCHEMA,
        "sharded_blueprint_sha256": design["sharded_blueprint_sha256"],
        "frozen_parent_commit": parent_sha,
        "required_external_engines": required,
        "source_verified": verified,
        "blocked_engines": blocked,
        "source_check_status": (
            "ALL_LOCAL_SOURCE_PINS_VERIFIED_NOT_RUN"
            if not blocked else "BLOCKED_VENDOR_SOURCE_NOT_ATTESTED"
        ),
        "external_vendor_started": False,
        "market_data_accessed": False,
        "independent_runner_attested": False,
        "engineering_acceptance_passed": False,
        "live_trading_authorized": False,
    }
    return {**body, "preflight_sha256":
            hashlib.sha256(_canonical(body)).hexdigest()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    args = parser.parse_args(argv)
    report = preflight_vendor_sources(
        _read_frozen(args.design), args.checkout)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if not report["blocked_engines"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
