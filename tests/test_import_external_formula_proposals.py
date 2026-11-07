"""Adversarial external formula intake contracts; no AI provider/network required."""
from __future__ import annotations

from dataclasses import asdict
import copy
import json
from pathlib import Path

import pytest

from norisk_quant.math_discovery import Formula
from scripts.import_external_formula_proposals import (
    SCHEMA, UPSTREAM_PINS, import_proposals, load_proposals,
)


def envelope(generator="openevolve"):
    return {
        "schema": SCHEMA, "generator": generator,
        "source_commit": UPSTREAM_PINS[generator][1],
        "proposals": [asdict(Formula(feature_a=1, threshold=1.0)),
                      asdict(Formula(feature_a=3, threshold=1.0))],
    }


def write(tmp_path, value):
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps(value))
    return path


def test_intake_imports_only_frozen_formula_to_private_output(tmp_path):
    path = write(tmp_path, envelope())
    out = tmp_path / "private"
    first = import_proposals(path, out)
    again = import_proposals(path, out)
    assert first == again
    assert first["formula_count"] == 2
    assert first["status"] == "PROPOSED_UNEVALUATED"
    manifest = json.loads((out / "external_intake_manifest.json").read_text())
    assert manifest["provenance_authenticated"] is False
    assert manifest["execution_performed"] is False
    assert manifest["independent_oos_proven"] is False
    assert manifest["live_trading_authorized"] is False
    assert manifest["upstream_repository"] == "algorithmicsuperintelligence/openevolve"
    formula_files = sorted(out.glob("formula_*.json"))
    assert len(formula_files) == 2
    assert all(set(json.loads(p.read_text())) == set(Formula.__dataclass_fields__)
               for p in formula_files)


@pytest.mark.parametrize("violation", ("unknown_generator", "revision",
        "unrecognized_field", "profit_score", "freeform_code", "holdout",
        "invalid_formula", "equivalent_alias", "many", "none"))
def test_intake_fails_closed_on_untrusted_external_outputs(tmp_path, violation):
    doc = envelope()
    if violation == "unknown_generator":
        doc["generator"] = "fake-agent"
    elif violation == "revision":
        doc["source_commit"] = "0" * 40
    elif violation == "unrecognized_field":
        doc["anything"] = 1
    elif violation == "profit_score":
        doc["proposals"][0]["fitness"] = 999999.0
    elif violation == "freeform_code":
        doc["proposals"][0]["python_code"] = "import os"
    elif violation == "holdout":
        doc["holdout_result"] = {"pnl": 99999}
    elif violation == "invalid_formula":
        doc["proposals"][0]["threshold"] = -100
    elif violation == "equivalent_alias":
        doc["proposals"][1] = copy.deepcopy(doc["proposals"][0])
        doc["proposals"][1]["threshold"] = 1
    elif violation == "many":
        doc["proposals"] *= 65
    else:
        doc["proposals"] = []
    with pytest.raises(ValueError):
        load_proposals(write(tmp_path, doc))


def test_intake_rejects_nonfinite_duplicate_key_and_symlink(tmp_path):
    a = tmp_path / "bad.json"
    a.write_text('{"schema": "X", "schema": "Y"}')
    with pytest.raises(ValueError, match="Duplicate"):
        load_proposals(a)
    a.write_text('{"schema": NaN}')
    with pytest.raises(ValueError, match="Nonfinite"):
        load_proposals(a)
    path = write(tmp_path, envelope())
    link = tmp_path / "aliased.json"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        load_proposals(link)


def test_intake_refuses_conflict_or_injection_to_existing_immutable_directory(tmp_path):
    path = write(tmp_path, envelope())
    out = tmp_path / "private"
    import_proposals(path, out)
    (out / "external_intake_manifest.json").write_text("tampered")
    with pytest.raises(ValueError, match="Conflicting"):
        import_proposals(path, out)


def test_intake_unauthorized_extra_file_rejected(tmp_path):
    path = write(tmp_path, envelope())
    out = tmp_path / "private"
    import_proposals(path, out)
    (out / "unexpected.py").write_text("print('untrusted')")
    with pytest.raises(ValueError, match="Unexpected"):
        import_proposals(path, out)
