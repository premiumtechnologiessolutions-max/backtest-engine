"""Private read-only independent audit of ONE finished historical batch.

Expects a previously frozen original source plan, original source-manifest
and the output directory. Never launches a backtest, broker/API call,
changes the SQLite queue, or publishes prices/strategy returns.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from norisk_quant.frozen_batch_attestation import verify_frozen_batch_evidence
from norisk_quant.source_registry import verify_record_manifest
from scripts import research_batch_orchestrator as batch


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan",required=True,type=Path)
    parser.add_argument("--source-manifest",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--experiment-id",required=True)
    options=parser.parse_args(argv)
    try:
        plan=batch.read_strict_json(options.plan)
        record=verify_record_manifest(batch.read_strict_json(options.source_manifest))
        if record.family != "original_gold_m1_bidask" or record.source_claim != "ORIGINAL_M1_DECLARED":
            raise ValueError("Original Gold M1 only")
        if record.source_file_sha256 != plan["source_sha256"]:
            raise ValueError("Frozen source does not match plan")
        audited=verify_frozen_batch_evidence(
            plan,options.output,
            expected_experiment_id=options.experiment_id,
            source_manifest_id=record.id,
        )
    except (OSError,ValueError,KeyError,TypeError):
        # Never echo untrusted private file paths, account information or
        # market source details from errors or the original output.
        parser.exit(2,"Frozen historical ledger re-audit rejected; no research executed.\n")
    print(json.dumps(audited.public_status(),sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
