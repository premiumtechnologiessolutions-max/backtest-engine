"""Fail-closed intake of external AI/GP Formula PROPOSALS, not their scores.

This is the explicit interface for tools such as OpenEvolve, RD-Agent and
AgonAlpha. No third-party runtime imports, eval, network, broker endpoints,
private Gold quotes, arbitrary Python or holdout data access occur here.

The declared upstream commit is allowlisted for reproducibility, but a
caller-supplied provenance claim is NOT authenticated upstream authorship.
Only the canonical frozen reference/fast executors may later evaluate proposals.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re

from norisk_quant.research_evolution import _formula
from scripts.materialize_arithmetic_generation import _encoded, _publish_once
from scripts.run_quant_research_platform import _safe_private_root

SCHEMA = "NRFX_EXTERNAL_FORMULA_INTAKE_V1"
MAX_BYTES = 128 * 1024
MAX_PROPOSALS = 128

# Source snapshots verified against upstream GitHub before this contract was made.
# This is an allowlist for asserted source revisions, NOT proof of provenance.
UPSTREAM_PINS = {
    "rd-agent": ("microsoft/RD-Agent", "484776c211e4fbbeef03e0ec00d6bbee7362a4f4", "MIT"),
    "openevolve": ("algorithmicsuperintelligence/openevolve",
                   "73448d715968b3578d8458b16295e827edd2b6bf", "Apache-2.0"),
    "agonalpha": ("AutoResearch-Factory/AgonAlpha",
                  "334f808df72d3da1ff78561d67700a7cf225af15", "MIT"),
}
_SHA = re.compile(r"[0-9a-f]{64}\Z")


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
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("External proposal source empty or oversized")
    try:
        data = json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid external proposal JSON") from exc
    if type(data) is not dict or set(data) != {
            "schema", "generator", "source_commit", "proposals"}:
        raise ValueError("External proposal contract refuses extra fields or scores")
    if data["schema"] != SCHEMA or data["generator"] not in UPSTREAM_PINS:
        raise ValueError("Unknown source or proposal schema")
    repo, commit, _license = UPSTREAM_PINS[data["generator"]]
    if type(data["source_commit"]) is not str or data["source_commit"] != commit:
        raise ValueError("Source revision not pinned to approved upstream")
    proposals = data["proposals"]
    if (type(proposals) is not list
            or not 1 <= len(proposals) <= MAX_PROPOSALS):
        raise ValueError("External proposal batch must have 1..128 formulas")
    canonical, seen = [], set()
    for row in proposals:
        # _formula validates a finite causal formula with exact frozen fields.
        # A submitted "code", "pnl", "score", "holdout" or "orders" key fails.
        formula = _formula(row)
        identity = formula.identity()
        if identity in seen:
            raise ValueError("Duplicate or equivalent external formula")
        seen.add(identity)
        canonical.append({"identity": identity, "formula": asdict(formula)})
    canonical.sort(key=lambda entry: entry["identity"])
    return {
        "schema": SCHEMA, "generator": data["generator"],
        "upstream_repository": repo, "upstream_commit_asserted": commit,
        "provenance_authenticated": False,
        "upstream_license_reported": _license,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "formula_count": len(canonical), "formulas": canonical,
        "status": "PROPOSED_UNEVALUATED",
        "independent_oos_proven": False,
        "live_trading_authorized": False,
        "execution_performed": False,
    }, raw


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
