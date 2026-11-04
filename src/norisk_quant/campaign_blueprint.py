"""Deterministic, INERT multi-engine quantitative research campaign blueprint.

This plans the end-to-end quant research DAG without executing any source
read, backtest, provider, AI agent, shell command, worker or broker order.
It is construction-phase engineering, NOT authorization to run the DAG.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import re

SCHEMA = "NRFX_QUANT_CAMPAIGN_BLUEPRINT_V1"
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_ID = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
_EXECUTION_ENGINES = frozenset({"norisk_quant", "lean", "nautilus"})
_AI_REVIEWERS = frozenset({"rd_agent", "tradingagents", "finrl"})
_STAGES = frozenset({
    "source_integrity", "causal_alignment", "strategy_compilation",
    "reference_simulation", "execution_reconciliation",
    "portfolio_risk", "failure_review", "report_assembly",
})
_MAX_STRATEGIES = 32
_MAX_TASKS = 512


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _sha(value: object, length: int) -> None:
    valid = _SHA40 if length == 40 else _SHA64
    if type(value) is not str or not valid.fullmatch(value):
        raise ValueError("Invalid immutable source fingerprint")


def _day(value: object) -> date:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Expected canonical UTC date")
    day = date.fromisoformat(value)
    if day.isoformat() != value:
        raise ValueError("Noncanonical date")
    return day


def _ids(value: object, *, allowed: frozenset, label: str,
         at_least_one: bool = True) -> tuple[str, ...]:
    if type(value) is not list or (at_least_one and not value):
        raise ValueError(f"Invalid {label} list")
    if len(value) > len(allowed) or any(
        type(x) is not str or x not in allowed for x in value
    ) or len(value) != len(set(value)):
        raise ValueError(f"Unexpected or repeated {label}")
    return tuple(sorted(value))


def _limits(value: object) -> dict:
    allowed = {"max_workers", "max_ram_mb", "max_disk_mb",
               "max_runtime_minutes"}
    if type(value) is not dict or set(value) != allowed:
        raise ValueError("Missing bounded resource policy")
    caps = {"max_workers": (1, 16), "max_ram_mb": (256, 262_144),
            "max_disk_mb": (256, 1_048_576),
            "max_runtime_minutes": (1, 10080)}
    for key, (minimum, maximum) in caps.items():
        v = value[key]
        if type(v) is not int or not minimum <= v <= maximum:
            raise ValueError(f"Invalid frozen resource limit: {key}")
    return dict(sorted(value.items()))


def _validate_and_normalize(spec: object) -> dict:
    fields = {"source_commit", "dataset", "evaluation", "strategies",
              "execution_engines", "ai_reviewers", "resource_limits",
              "all_in_cost_usd_per_ounce", "owner_policy"}
    if type(spec) is not dict or set(spec) != fields:
        raise ValueError("Campaign requires exact frozen schema")
    _sha(spec["source_commit"], 40)
    if spec["owner_policy"] != "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION":
        raise ValueError("Campaign execution permission is prohibited")
    if (type(spec["all_in_cost_usd_per_ounce"]) not in (int, float)
            or spec["all_in_cost_usd_per_ounce"] != 0.40):
        raise ValueError("Canonical roundtrip cost is exactly USD 0.40/oz")
    dataset = spec["dataset"]
    if (type(dataset) is not dict
            or set(dataset) != {"id", "archive_sha256", "start", "end", "format"}
            or type(dataset["id"]) is not str
            or not _ID.fullmatch(dataset["id"])
            or dataset["format"] != "M1_BID_ASK_ORIGINAL"):
        raise ValueError("Dataset identity and original quote format required")
    _sha(dataset["archive_sha256"], 64)
    ds_start, ds_end = _day(dataset["start"]), _day(dataset["end"])
    if ds_end < ds_start:
        raise ValueError("Dataset period inverted")
    evaluation = spec["evaluation"]
    if (type(evaluation) is not dict
            or set(evaluation) != {"start", "end", "scope"}
            or evaluation["scope"] != "UNEXECUTED_RESEARCH_DESIGN"):
        raise ValueError("Evaluation remains a frozen, unexecuted proposal")
    start, end = _day(evaluation["start"]), _day(evaluation["end"])
    if not ds_start <= start <= end <= ds_end:
        raise ValueError("Evaluation must lie within declared source period")
    strategies = spec["strategies"]
    if (type(strategies) is not list
            or not 1 <= len(strategies) <= _MAX_STRATEGIES):
        raise ValueError("Expected 1..32 frozen research strategies")
    normalized = []
    seen = set()
    for strategy in strategies:
        if (type(strategy) is not dict
                or set(strategy) != {"id", "code_sha256", "spec_sha256"}
                or type(strategy["id"]) is not str
                or not _ID.fullmatch(strategy["id"])
                or strategy["id"] in seen):
            raise ValueError("Noncanonical or repeated strategy")
        seen.add(strategy["id"])
        _sha(strategy["code_sha256"], 64)
        _sha(strategy["spec_sha256"], 64)
        normalized.append(dict(strategy))
    normalized.sort(key=lambda s: s["id"])
    engines = _ids(spec["execution_engines"], allowed=_EXECUTION_ENGINES,
                   label="reference engines")
    if "norisk_quant" not in engines:
        raise ValueError("No Risk FX reference engine is mandatory")
    reviewers = _ids(spec["ai_reviewers"], allowed=_AI_REVIEWERS,
                     label="AI research reviewers", at_least_one=False)
    if len(reviewers) > 0 and len(strategies) * (len(engines) + len(reviewers)) > 150:
        raise ValueError("Proposed AI/provider fanout exceeds safe construction budget")
    return {
        "source_commit": spec["source_commit"],
        "dataset": dict(dataset), "evaluation": dict(evaluation),
        "strategies": normalized,
        "execution_engines": list(engines),
        "ai_reviewers": list(reviewers),
        "resource_limits": _limits(spec["resource_limits"]),
        "all_in_cost_usd_per_ounce": 0.40,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    }


def _node(name: str, stage: str, depends: list[str], *,
          engine: str | None = None, strategy: str | None = None) -> dict:
    if stage not in _STAGES:
        raise ValueError("Unsupported research DAG stage")
    return {
        "id": name, "stage": stage, "depends_on": sorted(depends),
        "engine": engine, "strategy": strategy,
        "status": "DESIGNED_NOT_EXECUTED",
        "execution_enabled": False,
        "result_accepted": False,
    }


def freeze_blueprint(spec: dict) -> dict:
    """Compile a deterministic bounded DAG, NEVER schedule or run its nodes."""
    normalized = _validate_and_normalize(spec)
    nodes = [
        _node("source_integrity", "source_integrity", []),
        _node("causal_alignment", "causal_alignment", ["source_integrity"]),
    ]
    report_inputs = []
    for s in normalized["strategies"]:
        slug = s["id"]
        compiled = f"compile__{slug}"
        nodes.append(_node(compiled, "strategy_compilation",
                           ["causal_alignment"], strategy=slug))
        refs = []
        for engine in normalized["execution_engines"]:
            name = f"simulate__{slug}__{engine}"
            nodes.append(_node(name, "reference_simulation", [compiled],
                               engine=engine, strategy=slug))
            refs.append(name)
        reconciled = f"reconcile__{slug}"
        risk = f"risk__{slug}"
        nodes.append(_node(reconciled, "execution_reconciliation", refs,
                           strategy=slug))
        nodes.append(_node(risk, "portfolio_risk", [reconciled],
                           strategy=slug))
        report_inputs.append(risk)
        for reviewer in normalized["ai_reviewers"]:
            name = f"review__{slug}__{reviewer}"
            nodes.append(_node(name, "failure_review", [risk],
                               engine=reviewer, strategy=slug))
            report_inputs.append(name)
    nodes.append(_node("assemble_report", "report_assembly", report_inputs))
    if len(nodes) > _MAX_TASKS or len(nodes) != len({n["id"] for n in nodes}):
        raise ValueError("Duplicated or unbounded DAG")
    completed = set()
    for node in nodes:
        if any(dep not in completed for dep in node["depends_on"]):
            raise ValueError("DAG is not topologically ordered")
        completed.add(node["id"])
    payload = {
        "schema": SCHEMA,
        "normalized_spec": normalized,
        "spec_sha256": _digest(normalized),
        "dag": nodes,
        "node_count": len(nodes),
        "status": "ENGINEERING_BLUEPRINT_NOT_RUN",
        "worker_launch_authorized": False,
        "market_data_accessed": False,
        "provider_invoked": False,
        "strategy_backtested": False,
        "research_result_accepted": False,
        "live_trading_authorized": False,
        "independent_oos_proven": False,
    }
    return {**payload, "blueprint_sha256": _digest(payload)}


def verify_blueprint(blueprint: object) -> dict:
    """Recompile completely: a hash alone cannot legitimize a modified DAG."""
    if type(blueprint) is not dict or "normalized_spec" not in blueprint:
        raise ValueError("Missing frozen blueprint")
    restored = freeze_blueprint(blueprint["normalized_spec"])
    if blueprint != restored:
        raise ValueError("Modified or misleading research blueprint")
    return restored
