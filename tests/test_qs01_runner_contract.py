"""No private quotes needed: frozen QS01 design runner fail-closed contract."""
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from scripts.run_qs01_frozen_design import (
    SOURCE_SHA256, DESIGN_START, DESIGN_END, FROZEN, execute,
)
from scripts import run_qs01_frozen_design as zip_runner
from scripts.research_qs01_design import _require_design_month_observations


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


@pytest.mark.parametrize("suffix", ["", "reports/private-quotes"])
def test_qs01_zip_runner_refuses_output_within_source_repository(tmp_path, suffix):
    repository = Path(zip_runner.__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="outside the source repository"):
        execute(tmp_path / "missing.zip", repository / suffix)


def test_extracted_design_guard_requires_observations_in_every_month():
    observed = pd.date_range("2012-01-01", "2016-12-01", freq="MS", tz="UTC")
    _require_design_month_observations(pd.DataFrame(index=observed))
    missing = pd.DataFrame(index=observed[observed != pd.Timestamp("2014-06-01", tz="UTC")])
    with pytest.raises(ValueError, match="all 60 months.*2014-06"):
        _require_design_month_observations(missing)


def test_qs01_zip_runner_rejects_unobserved_month_before_generating_signals(tmp_path, monkeypatch):
    source = tmp_path / "Gold data.zip"
    source.write_bytes(b"synthetic source; checksum mocked")
    monkeypatch.setattr(zip_runner, "sha256_file", lambda _: SOURCE_SHA256)
    data = pd.DataFrame(index=pd.to_datetime(["2012-01-01", "2016-12-01"], utc=True))
    monkeypatch.setattr(zip_runner, "load_market", lambda *_: data)
    def unexpected_signal_generation(_):
        pytest.fail("Incomplete design source must fail before signal generation")
    monkeypatch.setattr(zip_runner, "qs01_signals", unexpected_signal_generation)
    with pytest.raises(ValueError, match="all 60 months"):
        execute(source, tmp_path / "results")
