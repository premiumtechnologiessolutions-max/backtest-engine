"""Prospective freezing without reading future market data or certifying an edge."""
from dataclasses import asdict
from datetime import date
from hashlib import sha256
import json

import pytest

from norisk_quant.math_discovery import Formula
from scripts import freeze_prospective_validation as freeze
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA


def make_input(tmp_path, *, eligible):
    path = tmp_path / "training.json"
    value = 1.0 if eligible else -1.0
    years = [2012, 2013]
    source = {
        "schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
        "years": years, "explored_ids": [],
        "candidates": [{"formula": asdict(Formula()), "records": [
            {"year": year, "metrics": {
                "months": {f"{year}-{month:02d}": value
                           for month in range(1, 13)},
                "net_usd_per_oz": 12 * value, "trades": 40,
                "fees_usd": 16.0,
                "positive_months": 12 if eligible else 0,
                "uncertain_gap_trades": 0,
                "synthetic_forced_closures": 0,
                "accounting": "PASSED",
            }} for year in years
        ]}],
    }
    raw = json.dumps(source).encode()
    path.write_bytes(raw)
    proof = {
        "schema": "NRFX_ARITHMETIC_FEEDBACK_EVIDENCE_V1",
        "next_input_sha256": sha256(raw).hexdigest(),
        "original_archive_sha256": SOURCE_SHA,
        "training_only": True, "independent_oos_proven": False,
        "live_trading_authorized": False,
        "training_years": years,
    }
    (tmp_path / "training.json.evidence.json").write_text(json.dumps(proof))
    return path


def do_freeze(path, out, **kw):
    return freeze.freeze_training_selection(
        path, start_date="2026-11-02", end_date="2027-01-29",
        output=out, as_of=date(2026, 10, 30), **kw)


def test_training_qualified_formula_frozen_without_looking_at_future(tmp_path):
    source = make_input(tmp_path, eligible=True)
    output = tmp_path / "future_freeze.json"
    result = do_freeze(source, output, top_n=1)
    doc = json.loads(output.read_text())
    assert result["candidates"] == 1
    assert doc["candidate_count"] == 1
    assert doc["fixed_all_in_cost_per_ounce"] == 0.40
    assert not doc["prospective_data_accessed"]
    assert not doc["independent_oos_proven"]
    assert not doc["live_trading_authorized"]
    assert result["freeze_sha256"] == sha256(output.read_bytes()).hexdigest()


def test_no_qualified_strategy_does_not_fake_oos_progress(tmp_path):
    source = make_input(tmp_path, eligible=False)
    output = tmp_path / "no_eligible.json"
    result = do_freeze(source, output)
    assert result["candidates"] == 0
    assert result["status"] == "NO_ELIGIBLE_TRAINING_CANDIDATES_NO_OOS"


def test_freeze_is_publish_once(tmp_path):
    source = make_input(tmp_path, eligible=True)
    output = tmp_path / "frozen.json"
    do_freeze(source, output)
    previous = output.read_bytes()
    with pytest.raises(ValueError, match="unused"):
        do_freeze(source, output)
    assert output.read_bytes() == previous


@pytest.mark.parametrize("start,end", [
    ("2026-10-25", "2026-12-31"),
    ("2026-11-01", "2026-11-10"),
    ("2026-11-02", "2026-11-20"),
])
def test_retrospective_or_short_horizon_cannot_be_frozen(tmp_path, start, end):
    source = make_input(tmp_path, eligible=True)
    output = tmp_path / "frozen.json"
    with pytest.raises(ValueError, match="Validation"):
        freeze.freeze_training_selection(
            source, start_date=start, end_date=end,
            output=output, as_of=date(2026, 10, 30))
    assert not output.exists()


def test_training_proof_tamper_is_rejected(tmp_path):
    source = make_input(tmp_path, eligible=True)
    source.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(ValueError, match="verified"):
        do_freeze(source, tmp_path / "freeze.json")


def test_later_training_year_cannot_be_called_future_independent(tmp_path):
    source = make_input(tmp_path, eligible=True)
    doc = json.loads(source.read_text())
    doc["years"][-1] = 2027
    source.write_text(json.dumps(doc))
    evidence_file = tmp_path / "training.json.evidence.json"
    proof = json.loads(evidence_file.read_text())
    proof["next_input_sha256"] = sha256(source.read_bytes()).hexdigest()
    proof["training_years"][-1] = 2027
    evidence_file.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="verified"):
        do_freeze(source, tmp_path / "frozen.json")
