"""Full frozen-generator -> actual batch expansion -> cross-year identity contract.

No source data loaded; no trading simulation or OOS claim.
"""
from scripts import generate_quant_research_grid as generator
from scripts import research_batch_orchestrator as batch
from scripts import research_cross_year_candidate_screen as cross


def test_frozen_factory_expands_to_228_identical_cross_year_strategy_identities(tmp_path):
    # make_plan only defines intent. freeze_plan separately authenticates source bytes.
    fake=tmp_path/"not-gold.zip"
    fake.write_bytes(b"NOT PRIVATE GOLD DATA")
    plan=generator.make_plan(fake,years=(2012,2013),
                             source_sha256=generator.SOURCE_SHA,
                             engine_commit="a"*40)
    jobs,plan_sha=batch.expand(plan)
    assert len(jobs)==456
    assert len(plan_sha)==64
    identities={}
    for job in jobs:
        key=cross.strategy_key(job["spec"])
        identities.setdefault(key,[]).append(job["spec"]["start"][:4])
    assert len(identities)==228
    assert all(sorted(years)==["2012","2013"] for years in identities.values())
    # No backtest is executed by the definition-only dry run.
    dry=batch.run_plan(plan,tmp_path/"unused",dry_run=True)
    assert dry["status"]=="DEFINED_ONLY_NO_BACKTEST"
    assert dry["jobs"]==456
    assert not (tmp_path/"unused").exists()
