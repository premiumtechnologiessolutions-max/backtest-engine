"""Freeze the ORB-01 private runner contract before reading annual results."""
import pytest

from scripts.run_frozen_opening_range import (
    DESIGN_YEARS, EXECUTION, SOURCE_SHA, SPEC, SPEC_SHA, execute,
)


def test_stage_1_years_and_fees_are_immutable():
    assert DESIGN_YEARS == (2012, 2013)
    assert EXECUTION.ounces == 1.0
    assert EXECUTION.roundtrip_cost_per_ounce == 0.40
    assert EXECUTION.max_entry_delay_minutes == 1
    assert EXECUTION.max_holding_minutes == 360
    assert SPEC['strategy']['start_hour_utc'] == 6
    assert SPEC['strategy']['reward_risk'] == 1.5
    assert len(SPEC_SHA) == len(SOURCE_SHA) == 64


def test_runner_rejects_unregistered_year_before_reading_data(tmp_path):
    with pytest.raises(ValueError, match='frozen'):
        execute(tmp_path / 'missing.zip', 2024, tmp_path / 'results')


def test_runner_rejects_unverified_source_before_loading_data(tmp_path):
    fake = tmp_path / 'fake.zip'
    fake.write_bytes(b'not gold')
    with pytest.raises(ValueError, match='SHA mismatch'):
        execute(fake, 2012, tmp_path / 'results')


def test_runner_never_overwrites_prior_result(tmp_path):
    import inspect
    assert 'if out.exists()' in inspect.getsource(execute)
