"""Static-only external engine adapter registry; NEVER imports or executes engines.

All integrations are construction-only until a separate explicit owner approval.
A capability name is documentation, not permission to fetch data or run jobs.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

_ALLOWED = frozenset({"LEAN", "NautilusTrader", "OpenBB", "RD-Agent", "TradingAgents", "FinRL"})
_DENIED = frozenset({"execute", "fetch", "network", "subprocess", "trade",
                     "backtest", "worker", "write_dataset", "benchmark", "replay"})
_SCHEMA = "NRFX_STATIC_ADAPTER_CONTRACT_V1"


@dataclass(frozen=True, slots=True)
class StaticAdapterContract:
    name: str
    purpose: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    owner_approved: bool = False
    execution_enabled: bool = False
    network_enabled: bool = False
    market_data_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if self.name not in _ALLOWED or type(self.purpose) is not str or not self.purpose:
            raise ValueError("Unknown or undocumented external adapter")
        if (not isinstance(self.inputs, tuple) or not isinstance(self.outputs, tuple)
                or not self.inputs or not self.outputs
                or any(type(x) is not str or not x or len(x) > 80
                       for x in (*self.inputs, *self.outputs))):
            raise ValueError("Adapter requires bounded static schema names")
        if any((self.owner_approved, self.execution_enabled,
                self.network_enabled, self.market_data_enabled,
                self.live_trading_enabled)):
            raise ValueError("External adapters are engineering-only and disabled")

    def manifest(self) -> dict:
        return {
            "schema": _SCHEMA,
            "adapter": self.name,
            "purpose": self.purpose,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "status": "DESIGN_ONLY_DISABLED",
            "owner_approved": False,
            "execution_enabled": False,
            "network_enabled": False,
            "market_data_enabled": False,
            "live_trading_enabled": False,
            "research_results_accepted": False,
        }


_CONTRACTS = (
    StaticAdapterContract("LEAN", "future offline execution adapter",
                          ("frozen_request_v1", "synthetic_quote_schema_v1"),
                          ("unverified_receipt_v1",)),
    StaticAdapterContract("NautilusTrader", "future offline event simulation adapter",
                          ("frozen_request_v1", "synthetic_quote_schema_v1"),
                          ("unverified_receipt_v1",)),
    StaticAdapterContract("OpenBB", "future optional data-provider mapping",
                          ("provider_descriptor_v1",), ("normalized_schema_v1",)),
    StaticAdapterContract("RD-Agent", "future research hypothesis exchange",
                          ("frozen_hypothesis_v1",), ("unverified_hypothesis_v1",)),
    StaticAdapterContract("TradingAgents", "future bounded analysis exchange",
                          ("frozen_analysis_request_v1",), ("unverified_analysis_v1",)),
    StaticAdapterContract("FinRL", "future offline model specification exchange",
                          ("frozen_model_spec_v1",), ("unverified_model_manifest_v1",)),
)
REGISTRY = MappingProxyType({item.name: item for item in _CONTRACTS})


def inspect_adapter(name: str) -> dict:
    """Return JSON-compatible inert metadata; no dynamic import or execution."""
    if type(name) is not str or name not in REGISTRY:
        raise ValueError("Unregistered external adapter")
    return REGISTRY[name].manifest()


def assert_construction_only(action: str) -> None:
    """Fail closed on any operational action, including unknown actions."""
    if type(action) is not str or action not in {"inspect", "describe", "validate_schema"}:
        raise PermissionError("ENGINE_CONSTRUCTION_ONLY: adapter action forbidden")
