"""Strict schema regression tests for causal sweep signal detector."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys

import pytest

path = Path(__file__).resolve().parents[1] / "scripts" / "detect_prior_session_sweeps.py"
spec = importlib.util.spec_from_file_location("sweep_schema_detector", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

T = datetime(2026, 10, 29, tzinfo=timezone.utc)


@pytest.mark.parametrize("threshold", [True, False, "0.5", None, float("nan"), float("inf"), 0, -1])
def test_invalid_threshold_fails_closed(threshold):
    with pytest.raises(ValueError):
        module.detect_prior_utc_day_sweeps([], min_sweep_usd=threshold)


@pytest.mark.parametrize("bad", [True, False, "100", None, float("nan"), float("inf"), -1, 0])
def test_invalid_ohlc_types_fail_closed(bad):
    with pytest.raises(ValueError):
        module.detect_prior_utc_day_sweeps([module.Bar(T, bad, 101, 99, 100)])


@pytest.mark.parametrize("bad_timestamp", [None, "2026-10-29", 42])
def test_invalid_timestamp_type_fails_closed(bad_timestamp):
    with pytest.raises(ValueError):
        module.detect_prior_utc_day_sweeps([module.Bar(bad_timestamp, 100, 101, 99, 100)])
