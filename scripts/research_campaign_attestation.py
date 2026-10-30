"""Immutable campaign intent and full-replay resume verification.

A cached summary is not permission to reuse results from a different seed,
training input, generation or execution protocol. Never touches holdout data.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from scripts.materialize_arithmetic_generation import (
    _encoded, _load_strict, _publish_once, _verified_generation, materialize,
)
from scripts.compile_arithmetic_training_feedback import compile_feedback
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA
from scripts.research_equity_cold_storage import (
    restore_equity_storage, freeze_equity_storage,
)

PLAN_SCHEMA = "NRFX_ARITHMETIC_CAMPAIGN_INTENT_V1"


def freeze_campaign_intent(root: Path, initial_input: Path, *, seed: int,
                           first_generation: int, proposal_count: int,
                           shard_size: int,
                           proposal_policy: str = "legacy_random") -> dict:
    """Create or verify a publish-once immutable campaign definition.

    Changing runtime disk/time limits or extending the requested generation
    count is allowed. Changing its research identity is never allowed.
    """
    if (any(type(v) is not int for v in
            (seed, first_generation, proposal_count, shard_size))
            or not 0 <= seed < 2**63 or first_generation < 1
            or not 1 <= proposal_count <= 128 or not 1 <= shard_size <= 128):
        raise ValueError("Invalid immutable campaign identity controls")
    if type(proposal_policy) is not str or proposal_policy not in (
            "legacy_random", "matched_guided_v1"):
        raise ValueError("Unknown immutable campaign policy")
    path = root / "campaign_intent.json"
    if root.is_symlink() or not root.is_dir() or path.is_symlink():
        raise ValueError("Unsafe campaign intent path")
    input_file = Path(initial_input)
    if input_file.is_symlink() or not input_file.is_file():
        raise ValueError("Original campaign training input is missing")
    _, source_sha = _load_strict(input_file)
    intent = {
        "schema": PLAN_SCHEMA, "initial_training_input_sha256": source_sha,
        "original_archive_sha256": SOURCE_SHA,
        "seed": seed, "first_generation": first_generation,
        "proposal_count": proposal_count, "shard_size": shard_size,
        "training_only": True, "independent_oos_proven": False,
        "live_trading_authorized": False,
    }
    if proposal_policy != "legacy_random":
        intent["proposal_policy"] = proposal_policy
    if path.exists():
        previous, digest = _load_strict(path)
        if previous != intent or digest != sha256(_encoded(intent)).hexdigest():
            raise ValueError("Immutable campaign intent differs: new campaign root required")
        return intent
    _publish_once(path, _encoded(intent))
    return intent


def attest_cached_generation(original_input: Path, folder: Path, *,
                             generation: int, seed: int,
                             proposal_count: int) -> dict:
    """Reaudit all cached reports and recompute lineage before allowing reuse.

    Validates deterministic generation and dispatch, and independently replays
    canonical feedback verification of every formula/year shard. No strategy
    backtests are re-executed, but trade/equity/report ledgers are reconciled.
    """
    if any(type(x) is not int for x in (generation, seed, proposal_count)):
        raise ValueError("Invalid cached generation controls")
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Unsafe cached generation directory")
    manifest = folder / "generation.json"
    dispatch_dir = folder / "dispatch"
    next_input = folder / "next_training_input.json"
    for path in (manifest, next_input):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Cached generation lacks immutable evidence")
    frozen_result, original_sha = _verified_generation(original_input, manifest)
    if (frozen_result["generation"] != generation
            or frozen_result["seed"] != seed
            or len(frozen_result["proposals"]) != proposal_count):
        raise ValueError("Cached generation belongs to different research controls")
    dispatch = materialize(original_input, manifest, dispatch_dir)
    if (dispatch["training_input_sha256"] != original_sha
            or dispatch["generation"] != generation):
        raise ValueError("Cached generation dispatch provenance mismatch")
    shards = sorted(folder.glob("replay_*"))
    if not shards or any(p.is_symlink() or not p.is_dir() for p in shards):
        raise ValueError("Cached generation has no safe annual replay shards")
    cold_storage = folder / "equity_cold_storage.json"
    if cold_storage.is_symlink():
        raise ValueError("Unsafe cold storage manifest")
    # Archived raw equity must be recovered and independently re-audited,
    # never trusted merely because a compressed digest exists.
    if cold_storage.is_file():
        restore_equity_storage(folder)
    result = compile_feedback(original_input, manifest, dispatch_dir,
                              shards, next_input)
    if result["status"] != "COMPLETE_EXPOSED_TRAINING_FEEDBACK_NOT_OOS":
        raise ValueError("Cached generation failed annual re-audit")
    if cold_storage.is_file():
        # Never discard raw forensic evidence after a failed re-audit.
        # Only return to compact cold state on complete acceptance.
        freeze_equity_storage(folder, prune_raw=True)
    return {
        "training_input_sha256": original_sha,
        "next_input_sha256": result["next_input_sha256"],
        "generation": generation,
        "replay_shards_reaudited": len(shards),
        "status": "CACHED_GENERATION_FULLY_REAUDITED_NOT_OOS",
    }
