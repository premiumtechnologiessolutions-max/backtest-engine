"""Synthetic-only annual grouping and train/review leakage regression tests."""
import copy
import pytest
from scripts import research_cross_year_candidate_screen as cross


def fixture(monkeypatch,tmp_path):
    source='a'*64;rev='b'*40
    plan={'source_sha256':source,'engine_commit':rev}
    jobs=[]; records={}
    for name in ('alpha','beta'):
        for y in (2012,2013,2014,2015):
            spec={"strategy":"ema","timeframe":"M15","execution":"reference",
                  "start":f"{y}-01-01","end":f"{y}-12-31",
                  "parameters":{"fast":8 if name=='alpha' else 9}}
            ident=f'{name}-{y}'
            jobs.append({'id':ident,'spec':spec})
            # Alpha wins all training months; beta wins all review months.
            val=(1. if name=='alpha' else -1.) if y in (2012,2013) else (-9. if name=='alpha' else 10.)
            records[ident]={"status":cross.batch.PASSED,
                "monthly_net_pnl":{f'{y}-{m:02d}':val for m in range(1,13)},
                "monthly_sha256":"ok", "uncertain_gap_trade_month_assignments":0,
                "synthetic_end_of_data_closures":0}
    manifest={"schema":cross.batch.SCHEMA,"plan_sha256":"p"*64,
        "source_sha256":source,"engine_commit":rev,"results":records}
    monkeypatch.setattr(cross.batch,'expand',lambda _: (jobs,'p'*64))
    monkeypatch.setattr(cross.batch,'audit_run',lambda folder,*a: records[folder.name].copy())
    monkeypatch.setattr(cross.batch,'read_ledger_csv',lambda folder:[
        {"period":m,"trades":"1"}
        for m in records[folder.parent.name]['monthly_net_pnl']])
    monkeypatch.setattr(cross.batch,'file_sha',lambda _: 'ok')
    settings=dict(train_years=(2012,2013),review_years=(2014,2015))
    return plan,manifest,records,settings,jobs


def test_cross_year_groups_same_parameters_and_ranks_only_training(monkeypatch,tmp_path):
    plan,manifest,records,settings,jobs=fixture(monkeypatch,tmp_path)
    first=cross.screen_cross_year(plan,manifest,tmp_path,**settings)
    assert first['candidate_identifiers']==2
    assert first['defined_annual_jobs']==8
    assert first['audited_annual_jobs']==8
    assert first['compared_candidates']==2
    assert first['research_status']=='HISTORICAL_EXPOSED_SCREEN_COMPLETE'
    assert [r['identity']['parameters']['fast'] for r in first['results']]==[8,9]
    assert first['results'][0]['train']['net_pnl_usd_per_oz']==24
    assert first['results'][0]['later_review_descriptive_only']['net_pnl_usd_per_oz']==-216
    assert first['results'][1]['later_review_descriptive_only']['net_pnl_usd_per_oz']==240
    assert first['results'][0]['training_screen']=='PASSED_EXPLORATORY'
    assert first['results'][1]['training_screen']=='REJECTED_EXPLORATORY'
    # Attack review outcomes: train selection MUST remain unchanged.
    for ident,record in records.items():
        if ident.endswith(('-2014','-2015')):
            record['monthly_net_pnl']={k:-10000*v for k,v in record['monthly_net_pnl'].items()}
    changed=cross.screen_cross_year(plan,manifest,tmp_path,**settings)
    for a,b in zip(first['results'],changed['results']):
        assert (a['candidate_id'],a['training_rank'],a['train'],a['training_screen']) == (
            b['candidate_id'],b['training_rank'],b['train'],b['training_screen'])


def test_missing_annual_run_does_not_certify_completed_comparison(monkeypatch,tmp_path):
    plan,manifest,records,settings,jobs=fixture(monkeypatch,tmp_path)
    manifest['results'].pop('alpha-2013')
    out=cross.screen_cross_year(plan,manifest,tmp_path,**settings)
    assert out['research_status']=='INCOMPLETE_ANNUAL_COVERAGE'
    assert out['compared_candidates']==1
    assert len(out['incomplete_candidates'])==1
    assert out['incomplete_candidates'][0]['missing_years']==[2013]
    assert out['results'][0]['training_rank'] is None
    assert out['results'][0]['training_screen']=='NOT_ELIGIBLE_BATCH_INCOMPLETE'


def test_forced_or_gap_exposure_cannot_pass_training_selection(monkeypatch,tmp_path):
    plan,manifest,records,settings,jobs=fixture(monkeypatch,tmp_path)
    records['alpha-2012']['synthetic_end_of_data_closures']=1
    records['alpha-2013']['uncertain_gap_trade_month_assignments']=1
    out=cross.screen_cross_year(plan,manifest,tmp_path,**settings)
    alpha=next(r for r in out['results'] if r['identity']['parameters']['fast']==8)
    assert alpha['train']['net_pnl_usd_per_oz']==24
    assert alpha['training_screen']=='REJECTED_EXPLORATORY'
    assert alpha['training_synthetic_forced_closes']==1
    assert alpha['training_uncertain_gap_trades']==1


def test_tampered_evidence_refused(monkeypatch,tmp_path):
    plan,manifest,records,settings,jobs=fixture(monkeypatch,tmp_path)
    snapshot=copy.deepcopy(records)
    monkeypatch.setattr(cross.batch,'audit_run',lambda folder,*a:snapshot[folder.name])
    manifest['results']['alpha-2012']['monthly_net_pnl']['2012-01'] += 100
    with pytest.raises(ValueError,match='changed'):
        cross.screen_cross_year(plan,manifest,tmp_path,**settings)


def test_duplicate_year_same_strategy_rejected(monkeypatch,tmp_path):
    plan,manifest,records,settings,jobs=fixture(monkeypatch,tmp_path)
    jobs.append({'id':'extra','spec':copy.deepcopy(jobs[0]['spec'])})
    with pytest.raises(ValueError,match='Repeated annual'):
        cross.screen_cross_year(plan,manifest,tmp_path,**settings)


@pytest.mark.parametrize('train,review', [
    ((2014,2015),(2013,)), ((2012,2013),(2013,2014)),
    ((),(2014,)), ((2012,),(2014,2013)),
])
def test_rejects_nonchronological_year_windows(monkeypatch,tmp_path,train,review):
    plan,manifest,records,settings,jobs=fixture(monkeypatch,tmp_path)
    with pytest.raises(ValueError):
        cross.screen_cross_year(plan,manifest,tmp_path,train_years=train,review_years=review)


def test_empty_partial_manifest_reports_unexecuted_not_performance(monkeypatch,tmp_path):
    plan,manifest,records,settings,jobs=fixture(monkeypatch,tmp_path)
    manifest['results'].clear()
    out=cross.screen_cross_year(plan,manifest,tmp_path,**settings)
    assert out['audited_annual_jobs']==0
    assert out['compared_candidates']==0
    assert out['research_status']=='INCOMPLETE_ANNUAL_COVERAGE'
    assert out['independent_oos_proven'] is False


def test_exact_joint_training_diagnostic_is_separate_from_selection(monkeypatch,tmp_path):
    plan, manifest, records, settings, jobs = fixture(monkeypatch,tmp_path)
    first = cross.screen_cross_year(plan,manifest,tmp_path,**settings)
    assert first["multiplicity_diagnostic"]["candidate_count"] == 2
    assert first["multiplicity_diagnostic"]["enumerated_joint_patterns"] == 4
    assert first["multiplicity_diagnostic"]["selection_or_live_authority"] == "NONE"
    assert first["multiplicity_diagnostic"]["independent_oos_proven"] is False
    snapshots = {
        row["candidate_id"]: row["training_signflip_diagnostic_only"]
        for row in first["results"]
    }
    # Review data changed after training; every diagnostic and rank remains
    # identical because no review month may enter train-only selection.
    for job_id, result in records.items():
        if job_id.endswith(("-2014", "-2015")):
            result["monthly_net_pnl"] = {m: -10 * val
                                          for m,val in result["monthly_net_pnl"].items()}
    after = cross.screen_cross_year(plan,manifest,tmp_path,**settings)
    assert {
        row["candidate_id"]: row["training_signflip_diagnostic_only"]
        for row in after["results"]
    } == snapshots


def test_incomplete_candidate_search_does_not_claim_adjusted_significance(monkeypatch,tmp_path):
    plan,manifest,records,settings,jobs = fixture(monkeypatch,tmp_path)
    manifest["results"].pop("alpha-2013")
    out = cross.screen_cross_year(plan,manifest,tmp_path,**settings)
    assert out["research_status"] == "INCOMPLETE_ANNUAL_COVERAGE"
    assert out["multiplicity_diagnostic"]["status"].startswith("NOT_COMPUTED")
    for row in out["results"]:
        assert row["training_rank"] is None
        assert "training_signflip_diagnostic_only" not in row
