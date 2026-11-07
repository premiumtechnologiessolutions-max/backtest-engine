"""Local code/spec byte attestation for frozen quant research design.

Does NOT execute strategy code, import external engines, read market archives,
validate Git ancestry, invoke AI or start a backtest. A SHA256 field supplied
by a caller is not evidence until the local bytes have been checked.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat

from norisk_quant.campaign_sharding import verify_sharded_campaign

SCHEMA = "NRFX_LOCAL_STRATEGY_SOURCE_AUDIT_V1"
_MAX_SOURCE_BYTES = 1_048_576


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _safe_path(root: Path, relative: object, *, kind: str) -> Path:
    if type(relative) is not str or "\\" in relative or relative.startswith("/"):
        raise ValueError("Noncanonical research source path")
    parts = PurePosixPath(relative).parts
    if (not parts or any(part in ("", ".", "..") for part in parts)
            or str(PurePosixPath(relative)) != relative):
        raise ValueError("Unsafe research source path")
    if kind == "code":
        if not relative.startswith("src/norisk_quant/") or not relative.endswith(".py"):
            raise ValueError("Strategy code must live under src/norisk_quant")
    elif kind == "spec":
        if (not relative.startswith(("docs/", "research/"))
                or not relative.endswith((".md", ".json"))):
            raise ValueError("Research spec must be a local markdown/JSON file")
    else:
        raise ValueError("Unknown research source role")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlinked strategy source path refused")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Research source missing or outside checkout")
    return path


def _read_source(root: Path, relative: str, *, kind: str) -> bytes:
    path = _safe_path(root, relative, kind=kind)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= _MAX_SOURCE_BYTES):
            raise ValueError("Source file must be unique, regular and bounded")
        data = stream.read(_MAX_SOURCE_BYTES + 1)
    if not 0 < len(data) <= _MAX_SOURCE_BYTES:
        raise ValueError("Source file exceeds bound")
    if kind == "code":
        try:
            ast.parse(data.decode("utf-8"), filename=relative)
        except (UnicodeError, SyntaxError) as exc:
            raise ValueError("Research Python source is not syntactically valid") from exc
    return data


def audit_campaign_sources(design: dict, repo_root: Path,
                           paths: dict[str, dict[str, str]]) -> dict:
    """Verify every strategy's code/spec hash against on-disk bytes.

    Strict all-strategy mapping: a shortlist cannot omit failed candidates.
    Does not claim the source_commit actually equals the checked out HEAD;
    verifying that requires a separate trusted Git attestation.
    """
    frozen = verify_sharded_campaign(design)
    root = Path(repo_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Unsafe checkout root")
    strategies = frozen["normalized_global_spec"]["strategies"]
    ids = {s["id"] for s in strategies}
    if type(paths) is not dict or set(paths) != ids:
        raise ValueError("Every frozen strategy requires an exact source mapping")
    evidence = []
    for strategy in strategies:
        strategy_id = strategy["id"]
        mapping = paths[strategy_id]
        if (type(mapping) is not dict
                or set(mapping) != {"code_path", "spec_path"}):
            raise ValueError("Strategy source mapping requires exactly code and spec")
        code = _read_source(root, mapping["code_path"], kind="code")
        spec = _read_source(root, mapping["spec_path"], kind="spec")
        code_digest, spec_digest = (
            hashlib.sha256(code).hexdigest(), hashlib.sha256(spec).hexdigest())
        if (code_digest != strategy["code_sha256"]
                or spec_digest != strategy["spec_sha256"]):
            raise ValueError("Frozen strategy source SHA256 differs from disk")
        evidence.append({
            "strategy_id": strategy_id,
            "code_path": mapping["code_path"],
            "spec_path": mapping["spec_path"],
            "code_sha256": code_digest,
            "spec_sha256": spec_digest,
            "code_size_bytes": len(code),
            "spec_size_bytes": len(spec),
        })
    body = {
        "schema": SCHEMA,
        "sharded_blueprint_sha256": frozen["sharded_blueprint_sha256"],
        "source_commit_declared": frozen["normalized_global_spec"]["source_commit"],
        "strategy_sources_checked": len(evidence),
        "strategy_sources": evidence,
        "local_code_and_specs_sha256_verified": True,
        "git_commit_ancestry_verified": False,
        "original_market_archive_verified": False,
        "source_read_only": True,
        "strategies_imported_or_executed": False,
        "independent_research_result_accepted": False,
    }
    return {**body, "audit_sha256": hashlib.sha256(_canonical(body)).hexdigest()}
