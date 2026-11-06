"""Fail-closed intake of external AI/GP Formula PROPOSALS, not their scores.

This is the explicit interface for tools such as OpenEvolve, RD-Agent,
TradingAgents and AgonAlpha. No third-party runtime imports, eval, network, broker endpoints,
private Gold quotes, arbitrary Python or holdout data access occur here.

The declared upstream commit is allowlisted for reproducibility, but a
caller-supplied provenance claim is NOT authenticated upstream authorship.
Only the canonical frozen reference/fast executors may later evaluate proposals.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from norisk_quant.lab_proposals import MAX_PROPOSALS, SCHEMA, UPSTREAM_PINS, proposal_intake_report
from scripts.materialize_arithmetic_generation import _encoded, _publish_once
from scripts.run_quant_research_platform import _safe_private_root

MAX_BYTES = 128 * 1024


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate external proposal JSON key")
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError("Nonfinite external proposal number")


def load_proposals(path: Path) -> tuple[dict, bytes]:
    """Load a small bounded JSON envelope; never parse or run generated code."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not path.is_absolute():
        raise ValueError("External intake source must be an absolute regular file")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("External proposal source exceeds 128 KiB")
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("External proposal source empty or oversized")
    try:
        data = json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid external proposal JSON") from exc
    report = proposal_intake_report(data)
    report["input_sha256"] = hashlib.sha256(raw).hexdigest()
    return report, raw


def import_proposals(source: Path, private_root: Path) -> dict:
    """Publish immutable private candidate files for the EXISTING CLI engine.

    Idempotent replay of identical input is allowed. Partial first writes can
    finish with the identical input. An altered manifest or extra file blocks.
    Inputs remain outside of the public checkout; no dataset is accessed.
    """
    report, _ = load_proposals(source)
    root = Path(private_root)
    if not root.is_absolute():
        raise ValueError("Private output root must be absolute")
    _safe_private_root(root)
    output = {}
    for item in report["formulas"]:
        name = "formula_" + item["identity"][:16] + ".json"
        output[name] = _encoded(item["formula"])
    manifest = dict(report)
    manifest["manifest_sha256"] = hashlib.sha256(_encoded(report)).hexdigest()
    output["external_intake_manifest.json"] = _encoded(manifest)
    # Reject unknown or changed local entries BEFORE any new publication.
    extra = {p.name for p in root.iterdir()} - set(output)
    if extra:
        raise ValueError("Unexpected content in private external-intake directory")
    for name, content in output.items():
        path = root / name
        if path.is_symlink() or (path.exists() and
                                (not path.is_file() or path.read_bytes() != content)):
            raise ValueError("Conflicting immutable external intake output")
    for name, content in output.items():
        if name != "external_intake_manifest.json":
            _publish_once(root / name, content)
    _publish_once(root / "external_intake_manifest.json",
                  output["external_intake_manifest.json"])
    return {"status": "PROPOSED_UNEVALUATED",
            "formula_count": len(report["formulas"]),
            "manifest_sha256": manifest["manifest_sha256"],
            "output_dir": str(root)}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="Small JSON envelope with only proposed formulas")
    parser.add_argument("--out", type=Path, required=True,
                        help="Private directory outside the public checkout")
    args = parser.parse_args(argv)
    print(json.dumps(import_proposals(args.input, args.out), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

