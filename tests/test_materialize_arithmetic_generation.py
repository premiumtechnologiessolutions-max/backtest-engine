"""End-to-end training evolution -> immutable canonical CLI formula dispatch."""
from dataclasses import asdict
import copy
from hashlib import sha256
import json

import pytest

from norisk_quant.math_discovery import Formula
from scripts.materialize_arithmetic_generation import materialize
from scripts.run_arithmetic_evolution import run


def _training():
    return {
        "schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
        "years": [2012, 2013],
        "explored_ids": [],
        "candidates": [{
            "formula": asdict(Formula()),
            "records": [{
                "year": year,
                "metrics": {
                    "months": {f"{year}-{m:02d}": 1.0 for m in range(1, 13)},
                    "net_usd_per_oz": 12.0, "trades": 45, "fees_usd": 18.0,
                    "positive_months": 12, "uncertain_gap_trades": 0,
                    "synthetic_forced_closures": 0, "accounting": "PASSED",
                },
            } for year in (2012, 2013)],
        }],
    }


@pytest.fixture
def frozen(tmp_path):
    source = tmp_path / "training.json"
    generation = tmp_path / "generation.json"
    source.write_text(json.dumps(_training()))
    run(source, generation, seed=17, generation=1, proposal_count=5)
    return source, generation, tmp_path / "dispatch"


def test_dispatch_replays_training_and_emits_cli_compatible_full_formulas(frozen):
    source, generation, directory = frozen
    result = materialize(source, generation, directory)
    assert result["formula_count"] == 5
    assert result["execution_contract"] == {
        "strategy": "arithmetic", "timeframe": "M1",
        "all_in_cost_per_ounce": 0.40, "backtests_executed": False,
    }
    assert result["independent_oos_proven"] is False
    assert result["live_trading_authorized"] is False
    assert set(p.name for p in directory.iterdir()) == {
        "dispatch_index.json", *(row["relative_path"] for row in result["formulas"])
    }
    for row in result["formulas"]:
        path = directory / row["relative_path"]
        assert sha256(path.read_bytes()).hexdigest() == row["file_sha256"]
        assert Formula(**json.loads(path.read_text())).identity() == row["identity"]
    assert json.loads((directory / "dispatch_index.json").read_text()) == result
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    assert materialize(source, generation, directory) == result
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}


@pytest.mark.parametrize("change", ["formula_type_alias", "formula_change",
                                    "digest", "extra_key", "nonfinite"])
def test_tampered_generation_is_rejected_before_dispatch(frozen, change):
    source, generation, directory = frozen
    manifest = json.loads(generation.read_text())
    if change == "formula_type_alias":
        formula = manifest["result"]["proposals"][0]["formula"]
        formula["lookback"] = float(formula["lookback"])  # 20 != 20.0 in JSON
    elif change == "formula_change":
        manifest["result"]["proposals"][0]["formula"]["threshold"] = 7.9
    elif change == "digest":
        manifest["result"]["manifest_sha256"] = "0" * 64
    elif change == "extra_key":
        manifest["result"]["independent_oos_result"] = 999
    elif change == "nonfinite":
        manifest["result"]["proposals"][0]["formula"]["threshold"] = float("inf")
    generation.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, TypeError)):
        materialize(source, generation, directory)
    assert not directory.exists()


def test_training_source_change_or_duplicate_json_rejected(frozen):
    source, generation, directory = frozen
    original = source.read_text()
    source.write_text(original.replace('"years": [2012, 2013]',
                                            '"years": [2012, 2014]'))
    with pytest.raises(ValueError):
        materialize(source, generation, directory)
    assert not directory.exists()
    source.write_text(original)
    generation.write_text(generation.read_text().replace(
        '"input_sha256":', '"input_sha256": "bogus", "input_sha256":', 1))
    with pytest.raises(ValueError, match="Duplicate"):
        materialize(source, generation, directory)
    assert not directory.exists()


def test_resume_only_missing_files_and_refuse_existing_tamper(frozen):
    source, generation, directory = frozen
    result = materialize(source, generation, directory)
    missing = directory / result["formulas"][2]["relative_path"]
    expected = missing.read_bytes()
    missing.unlink()
    materialize(source, generation, directory)
    assert missing.read_bytes() == expected
    missing.write_text('{"lookback": 5}')
    with pytest.raises(ValueError, match="differs"):
        materialize(source, generation, directory)
    assert missing.read_text() == '{"lookback": 5}'


def test_reject_unexpected_file_and_symlink_outputs(frozen):
    source, generation, directory = frozen
    materialize(source, generation, directory)
    rogue = directory / "extra.txt"
    rogue.write_text("unexpected")
    with pytest.raises(ValueError, match="Unexpected"):
        materialize(source, generation, directory)
    rogue.unlink()
    index = directory / "dispatch_index.json"
    index.unlink()
    index.symlink_to(source)
    with pytest.raises(ValueError, match="differs"):
        materialize(source, generation, directory)
    assert source.read_text().startswith('{"schema"')


def test_reject_output_directory_symlink(frozen, tmp_path):
    source, generation, directory = frozen
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    directory.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError, match="real directory"):
        materialize(source, generation, directory)
    assert list(elsewhere.iterdir()) == []
