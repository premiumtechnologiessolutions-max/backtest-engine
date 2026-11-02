"""Static deployment contracts; no host or market-data access."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_watchdog_unit_runs_read_only_check():
    unit = (ROOT / "deploy/norisk-quant-healthcheck.service").read_text()
    assert "Type=oneshot" in unit
    assert "research_unattended_healthcheck" in unit
    assert "ReadOnlyPaths=/srv/noriskfx-private" in unit
    assert "User=noriskfx" in unit
    assert "StandardOutput=journal" in unit
    assert "ExecStart=" in unit
    assert "curl" not in unit and "telegram" not in unit.lower()


def test_timer_is_bound_to_watchdog_not_research():
    timer = (ROOT / "deploy/norisk-quant-healthcheck.timer").read_text()
    assert "OnBootSec=2min" in timer
    assert "OnUnitInactiveSec=2min" in timer
    assert "Unit=norisk-quant-healthcheck.service" in timer
    assert "WantedBy=timers.target" in timer


def test_worker_remains_separate_from_watchdog():
    worker = (ROOT / "deploy/norisk-quant-research.service").read_text()
    assert "research_unattended_service run" in worker
    assert "RestartPreventExitStatus=1 2" in worker
    assert "research_unattended_healthcheck" not in worker
