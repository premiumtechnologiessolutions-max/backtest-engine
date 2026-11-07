"""Adversarial training-only deterministic evolution tests."""
from dataclasses import asdict
import copy
import math
import pytest
from norisk_quant.math_discovery import Formula
from norisk_quant.research_evolution import evolve_training_generation

YEARS=(2012,2013)

def evidence(formula, monthly=1.0):
    return {"formula":asdict(formula), "records":[
        {"year":y, "metrics":{
            "months":{f"{y}-{m:02d}":monthly for m in range(1,13)},
            "net_usd_per_oz":monthly*12, "trades":45,
            "fees_usd":18.0, "positive_months":12 if monthly>0 else 0,
            "uncertain_gap_trades":0,"synthetic_forced_closures":0,
            "accounting":"PASSED"}} for y in YEARS]}


def test_deterministic_unique_and_lineage_from_evaluated_training_only():
    rows=[evidence(Formula(),1),evidence(Formula(feature_a=1),-1)]
    a=evolve_training_generation(rows,YEARS,seed=18,generation=1,proposal_count=16)
    b=evolve_training_generation(rows[::-1],YEARS,seed=18,generation=1,proposal_count=16)
    assert a==b
    assert len(a["proposals"])==16
    assert len({x["identity"] for x in a["proposals"]})==16
    assert all(x["parent_identity"] in {Formula().identity(),Formula(feature_a=1).identity()} for x in a["proposals"])
    assert all(Formula(**x["formula"]).identity()==x["identity"] for x in a["proposals"])
    assert a["independent_oos_proven"] is False
    assert a["live_trading_authorized"] is False
    assert a["rankings"][0]["identity"]==Formula().identity()
    assert a["manifest_sha256"]==b["manifest_sha256"]


def test_explored_id_exclusion_and_no_global_rng_dependency():
    rows=[evidence(Formula())]
    first=evolve_training_generation(rows,YEARS,seed=3,generation=0,proposal_count=4)
    ids=tuple(x["identity"] for x in first["proposals"])
    second=evolve_training_generation(rows,YEARS,seed=3,generation=0,proposal_count=4,explored_ids=ids)
    assert not set(ids)&{x["identity"] for x in second["proposals"]}
    assert first!=second


@pytest.mark.parametrize("corrupt",[
    lambda rows:rows[0]["records"].pop(),
    lambda rows:rows[0]["records"].append(copy.deepcopy(rows[0]["records"][0])),
    lambda rows:rows[0]["records"][0]["metrics"]["months"].pop("2012-01"),
    lambda rows:rows[0]["records"][0]["metrics"].update({"fees_usd":0}),
    lambda rows:rows[0]["records"][0]["metrics"].update({"oos_net":999999}),
    lambda rows:rows[0].update({"holdout_result":100000}),
    lambda rows:rows[0]["formula"].update({"feature_a":True}),
    lambda rows:rows[0]["formula"].update({"extra":1}),
    lambda rows:rows[0]["records"][0]["metrics"].update({"net_usd_per_oz":math.inf}),
])
def test_incomplete_tampered_or_holdout_contaminated_evidence_rejected(corrupt):
    rows=[evidence(Formula())]
    corrupt(rows)
    with pytest.raises(ValueError):
        evolve_training_generation(rows,YEARS,seed=1,generation=0)


def test_duplicate_evaluated_formulas_rejected():
    rows=[evidence(Formula()),evidence(Formula())]
    with pytest.raises(ValueError): evolve_training_generation(rows,YEARS,seed=1,generation=0)


@pytest.mark.parametrize("kwargs",[
    {"seed":True},{"seed":-1},{"seed":2**63},{"generation":-1},
    {"generation":True},{"proposal_count":0},{"proposal_count":129},
    {"proposal_count":True},{"explored_ids":["a"*64]},
    {"explored_ids":("invalid",)},
    {"explored_ids":("a"*64,"a"*64)},
])
def test_reject_invalid_controls(kwargs):
    options=dict(seed=1,generation=0)
    options.update(kwargs)
    with pytest.raises(ValueError):
        evolve_training_generation([evidence(Formula())],YEARS,**options)


def test_reject_noncanonical_training_year_universe():
    with pytest.raises(ValueError):
        evolve_training_generation([evidence(Formula())],(2013,2012),seed=1,generation=0)


def test_equivalent_integer_and_float_parameters_cannot_double_count_training():
    # The Formula grammar permits 1 and 1.0, but these are one strategy.
    integer = evidence(Formula(threshold=1, stop_usd=8, reward_risk=1))
    floating = evidence(Formula(threshold=1.0, stop_usd=8.0, reward_risk=1.0))
    # Python dict equality considers 1 == 1.0; their raw JSON IDs differ.
    assert Formula(**integer["formula"]).identity() != Formula(**floating["formula"]).identity()
    with pytest.raises(ValueError, match="Duplicate evaluated formula"):
        evolve_training_generation([integer, floating], YEARS,
                                   seed=7, generation=0)


def test_numeric_aliases_produce_identical_training_evolution_manifest():
    integer = evidence(Formula(threshold=1, stop_usd=8, reward_risk=1))
    floating = evidence(Formula(threshold=1.0, stop_usd=8.0, reward_risk=1.0))
    a = evolve_training_generation([integer], YEARS,
                                   seed=7, generation=0, proposal_count=5)
    b = evolve_training_generation([floating], YEARS,
                                   seed=7, generation=0, proposal_count=5)
    assert a == b
