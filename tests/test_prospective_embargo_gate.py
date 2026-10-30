"""Synthetic anti-leakage regressions for publish-once prospective research plans."""
from dataclasses import asdict
from datetime import date
from hashlib import sha256
import json

import pytest

from norisk_quant.math_discovery import Formula
from scripts import freeze_prospective_validation as freeze
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA


def training(tmp_path, years=(2012, 2013), *, duplicate=False):
    path = tmp_path / "training.json"
    candidate = {
        "formula": asdict(Formula()),
        "records": [{
            "year": year,
            "metrics": {
                "months": {f"{year}-{m:02d}": 1.0 for m in range(1, 13)},
                "net_usd_per_oz": 12.0, "trades": 40, "fees_usd": 16.0,
                "positive_months": 12, "uncertain_gap_trades": 0,
                "synthetic_forced_closures": 0, "accounting": "PASSED",
            },
        } for year in years],
    }
    payload = {
        "schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
        "years": list(years),
        "candidates": [candidate, candidate] if duplicate else [candidate],
    }
    raw = json.dumps(payload).encode("utf-8")
    path.write_bytes(raw)
    proof = {
        "schema": "NRFX_ARITHMETIC_FEEDBACK_EVIDENCE_V1",
        "next_input_sha256": sha256(raw).hexdigest(),
        "original_archive_sha256": SOURCE_SHA,
        "training_years": list(years),
        "training_only": True,
        "independent_oos_proven": False,
        "live_trading_authorized": False,
    }
    path.with_name(path.name + ".evidence.json").write_text(json.dumps(proof))
    return path


def attempt(path, output, *, start="2026-11-02", end="2027-01-29",
            today=date(2026, 10, 30), embargo_days=30):
    return freeze.freeze_training_selection(
        path, start_date=start, end_date=end, output=output,
        as_of=today, embargo_days=embargo_days,
    )


@pytest.mark.parametrize("start,end", [
    ("2026-W45-1", "2027-01-29"),
    ("2026-11-02", "2027-W04-5"),
    ("20261102", "2027-01-29"),
    ("2026-11-02T00:00:00", "2027-01-29"),
])
def test_only_canonical_iso_calendar_dates(tmp_path, start, end):
    path = training(tmp_path)
    out = tmp_path / "freeze.json"
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        attempt(path, out, start=start, end=end)
    assert not out.exists()


@pytest.mark.parametrize("years", [
    (2013, 2012), (2012, 2012), (2012, True),
])
def test_invalid_or_repeated_training_years_cannot_be_certified(tmp_path, years):
    path = training(tmp_path, years=years)
    out = tmp_path / "freeze.json"
    with pytest.raises(ValueError, match="unique, sorted integers"):
        attempt(path, out)
    assert not out.exists()


def test_repeated_formula_identity_cannot_fill_multiple_candidate_slots(tmp_path):
    path = training(tmp_path, duplicate=True)
    out = tmp_path / "freeze.json"
    with pytest.raises(ValueError, match="Duplicate candidate identity"):
        attempt(path, out)
    assert not out.exists()


def test_embargo_blocks_nearby_prospective_period_and_records_verified_gap(tmp_path):
    path = training(tmp_path, years=(2025,))
    out = tmp_path / "freeze.json"
    with pytest.raises(ValueError, match="embargo"):
        attempt(path, out, start="2026-01-15", end="2026-03-15",
                today=date(2025, 12, 30))
    assert not out.exists()
    result = attempt(path, out, start="2026-02-05", end="2026-04-05",
                     today=date(2025, 12, 30))
    frozen = json.loads(out.read_text())
    assert result["candidates"] == 1
    assert frozen["last_training_calendar_date"] == "2025-12-31"
    assert frozen["embargo_days_after_training"] == 30
    assert frozen["training_embargo_verified"] is True
    assert frozen["independent_oos_proven"] is False
    assert frozen["live_trading_authorized"] is False


@pytest.mark.parametrize("days", [True, 0, -1, 367, 1.5])
def test_embargo_policy_cannot_be_disabled_or_coerced(tmp_path, days):
    path = training(tmp_path)
    out = tmp_path / "freeze.json"
    with pytest.raises(ValueError, match="Embargo"):
        attempt(path, out, embargo_days=days)
    assert not out.exists()
