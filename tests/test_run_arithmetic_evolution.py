"""Offline CLI evidence persistence and strict JSON contract tests."""
from dataclasses import asdict
import json
from pathlib import Path
import pytest
from norisk_quant.math_discovery import Formula
from run_arithmetic_evolution import run


def payload():
    return {"schema":"NRFX_ARITHMETIC_TRAINING_INPUT_V1",
            "years":[2012,2013],"explored_ids":[],"candidates":[{
                "formula":asdict(Formula()),
                "records":[{"year":y,"metrics":{
                    "months":{f"{y}-{m:02d}":1. for m in range(1,13)},
                    "net_usd_per_oz":12.,"trades":45,"fees_usd":18.,
                    "positive_months":12,"uncertain_gap_trades":0,
                    "synthetic_forced_closures":0,"accounting":"PASSED"}}
                           for y in (2012,2013)]}]}


def test_write_once_resume_and_refuse_changed_evidence(tmp_path):
    source=tmp_path/'in.json';out=tmp_path/'out.json'
    source.write_text(json.dumps(payload()))
    first=run(source,out,seed=5,generation=1,proposal_count=6)
    assert first==run(source,out,seed=5,generation=1,proposal_count=6)
    assert len(first['result']['proposals'])==6
    assert json.loads(out.read_text())==first
    before=out.read_bytes()
    with pytest.raises(ValueError,match='refusing'):
        run(source,out,seed=6,generation=1,proposal_count=6)
    assert out.read_bytes()==before


@pytest.mark.parametrize('mutate',[
    lambda text: text.replace('"years":', '"years": [2012,2013], "years":',1),
    lambda text: text.replace('12.0','NaN',1),
    lambda text: text.replace('"explored_ids": []','"holdout_results": []',1),
])
def test_malformed_duplicate_or_contaminated_json_fails_closed(tmp_path,mutate):
    source=tmp_path/'in.json';out=tmp_path/'out.json'
    source.write_text(mutate(json.dumps(payload())))
    with pytest.raises(ValueError): run(source,out,seed=5,generation=1,proposal_count=3)
    assert not out.exists()


def test_never_rewrite_input_and_reject_same_path(tmp_path):
    source=tmp_path/'input.json'
    source.write_text(json.dumps(payload()))
    with pytest.raises(ValueError):run(source,source,seed=1,generation=0,proposal_count=2)
