"""Dashboard renders synthetic, SHA-verified training only; no raw M1 prices."""
from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from norisk_quant.math_discovery import Formula
from scripts import research_training_dashboard as dash
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA


def fixture(tmp_path):
    root = tmp_path / "runs"
    gen = root / "generation_0001"
    gen.mkdir(parents=True)
    source = {"schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
              "years": [2012, 2013], "explored_ids": [], "candidates": [{
                  "formula": asdict(Formula()),
                  "records": [{"year": y, "metrics": {
                      "months": {f"{y}-{m:02d}": 1.0 for m in range(1, 13)},
                      "net_usd_per_oz": 12.0, "trades": 40,
                      "fees_usd": 16.0, "positive_months": 12,
                      "uncertain_gap_trades": 0, "synthetic_forced_closures": 0,
                      "accounting": "PASSED",
                  }} for y in (2012, 2013)],
              }]}
    content = json.dumps(source).encode()
    (gen / "next_training_input.json").write_bytes(content)
    proof = {"schema": "NRFX_ARITHMETIC_FEEDBACK_EVIDENCE_V1",
             "training_only": True, "independent_oos_proven": False,
             "live_trading_authorized": False,
             "original_archive_sha256": SOURCE_SHA,
             "next_input_sha256": sha256(content).hexdigest(),
             "training_years": [2012, 2013], "evaluated_formulas": 1,
             "complete_formula_year_pairs": 2}
    (gen / "next_training_input.json.evidence.json").write_text(json.dumps(proof))
    return root, gen


def test_verified_private_dashboard_and_strategy_comparison(tmp_path):
    root, gen = fixture(tmp_path)
    output = tmp_path / "research.html"
    result = dash.build_dashboard(root, output)
    html = output.read_text()
    assert result["generations"] == 1
    assert result["comparison_rows"] == 1
    assert "TRAINING ONLY" in html and "NOT INDEPENDENT OOS" in html
    assert "24/24" in html
    assert "NO RISK FX" in html
    assert result["independent_oos_proven"] is False
    assert result["sha256"] == sha256(output.read_bytes()).hexdigest()


def test_incomplete_generation_must_not_infer_results(tmp_path):
    root = tmp_path / "runs"
    (root / "generation_0001").mkdir(parents=True)
    result = dash.read_evidence(root)
    assert result[0]["status"] == "INCOMPLETE_NOT_CERTIFIED"
    assert result[0]["items"] == []


def test_tampered_feedback_digest_fails_closed(tmp_path):
    root, gen = fixture(tmp_path)
    doc = gen / "next_training_input.json"
    doc.write_bytes(doc.read_bytes() + b" ")
    with pytest.raises(ValueError, match="mismatch"):
        dash.read_evidence(root)


def test_prospective_claim_is_never_accepted(tmp_path):
    root, gen = fixture(tmp_path)
    proof_path = gen / "next_training_input.json.evidence.json"
    proof = json.loads(proof_path.read_text())
    proof["independent_oos_proven"] = True
    proof_path.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="mismatch"):
        dash.read_evidence(root)


def test_no_private_dashboard_output_inside_evidence(tmp_path):
    root, gen = fixture(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        dash.build_dashboard(root, root / "private.html")
    assert not (root / "private.html").exists()
