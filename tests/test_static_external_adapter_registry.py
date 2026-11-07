"""Pure synthetic static contract tests: no external packages imported."""
import pytest

from scripts.static_external_adapter_registry import (
    REGISTRY, StaticAdapterContract, inspect_adapter,
    assert_construction_only,
)


def test_six_known_integrations_are_inert_and_documented():
    assert set(REGISTRY) == {
        "LEAN", "NautilusTrader", "OpenBB", "RD-Agent", "TradingAgents", "FinRL"
    }
    for name in REGISTRY:
        result = inspect_adapter(name)
        assert result["status"] == "DESIGN_ONLY_DISABLED"
        assert result["research_results_accepted"] is False
        for flag in ("owner_approved", "execution_enabled", "network_enabled",
                     "market_data_enabled", "live_trading_enabled"):
            assert result[flag] is False
        assert result["inputs"] and result["outputs"]


@pytest.mark.parametrize("action", [
    "execute", "fetch", "network", "subprocess", "trade", "backtest",
    "worker", "write_dataset", "benchmark", "replay", "unknown", "", None,
])
def test_all_operational_actions_fail_closed(action):
    with pytest.raises(PermissionError):
        assert_construction_only(action)


def test_only_inert_actions_are_allowed():
    for action in ("inspect", "describe", "validate_schema"):
        assert assert_construction_only(action) is None


def test_registry_rejects_unknown_or_enabled_adapter():
    with pytest.raises(ValueError):
        inspect_adapter("not-registered")
    with pytest.raises(ValueError):
        StaticAdapterContract("LEAN", "unsafe", ("request",), ("receipt",),
                              execution_enabled=True)
    with pytest.raises(ValueError):
        StaticAdapterContract("OpenBB", "unsafe", ("request",), ("receipt",),
                              network_enabled=True)


def test_registry_cannot_be_mutated():
    with pytest.raises(TypeError):
        REGISTRY["custom"] = object()
