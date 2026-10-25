"""No private quotes needed: frozen QS01 design runner fail-closed contract."""
import zipfile

import pytest

from scripts.run_qs01_frozen_design import (
    SOURCE_SHA256, DESIGN_START, DESIGN_END, FROZEN, execute,
)


def test_qs01_frozen_runner_contract():
    assert len(SOURCE_SHA256) == 64
    assert (DESIGN_START, DESIGN_END) == ("2012-01-01", "2016-12-31")
    assert FROZEN.ounces == 1.0
    assert FROZEN.roundtrip_cost_per_ounce == 0.40
    assert FROZEN.max_entry_delay_minutes == 0
    assert FROZEN.max_hold_minutes == 30


def test_qs01_refuses_unknown_quote_archive_before_reading(tmp_path):
    source = tmp_path / "Gold data.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("2012.json", "[]")
    with pytest.raises(ValueError, match="SHA mismatch"):
        execute(source, tmp_path / "results")


def test_qs01_refuses_unknown_execution_backend(tmp_path):
    with pytest.raises(ValueError, match="Execution"):
        execute(tmp_path / "missing.zip", tmp_path / "results", execution="optimistic")
