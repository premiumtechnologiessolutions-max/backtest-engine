"""Design-only experiment counts and safety rules; no market data replay."""
import json
from pathlib import Path

import pytest
from scripts import generate_quant_research_grid as factory


def test_default_preview_defines_3192_completed_year_specifications(capsys):
    assert factory.main(["--dry-run"]) == 0
    report=json.loads(capsys.readouterr().out)
    assert report["status"] == "DEFINED_ONLY_NO_BACKTEST"
    assert report["candidate_definitions"] == 3192
    assert report["grid_families"] == 84
    assert report["not_independent_oos"] is True


def test_grid_family_counts_and_no_accidental_duplicates():
    years=(2012,2013)
    a=factory.grids(years)
    assert a == factory.grids(years)
    assert len(a)==12
    assert factory.count_definitions(a)==456
    assert len({g["id_prefix"] for g in a})==len(a)
    assert {g["strategy"] for g in a}=={"m1-sweep","tf-sweep","bos-fib","fvg"}
    assert all(g["execution"]=="reference" for g in a)
    assert all(g["strategy"]!="m1-sweep" or g["timeframe"]=="M1" for g in a)
    fib=[g for g in a if g["strategy"]=="bos-fib"]
    assert all(g["grid"]["bos_fib_entry"]==[.50,.62,.705,.79,.87] for g in fib)


@pytest.mark.parametrize("bad", [
    "", "2012,", "2012,2012", "2013,2012", "2012,,2013",
    "2012, 2013", "2009", "2027", "2011-2012", "abcd", 2012,
])
def test_bad_years_fail_closed(bad):
    with pytest.raises(ValueError):
        factory.parse_years(bad)


def test_good_years_accepted_with_single_year():
    assert factory.parse_years("2012")==(2012,)
    assert factory.parse_years("2010,2017,2026")== (2010,2017,2026)


def test_empty_grid_and_out_of_range_rejected():
    with pytest.raises(ValueError): factory.grids(())
    with pytest.raises(ValueError): factory.grids((2014,2012))
    with pytest.raises(ValueError): factory.grids((2027,))
    with pytest.raises(ValueError): factory.grids((True,))


def test_plan_freezes_historical_exposure_and_original_sha_contract(tmp_path):
    file=tmp_path/"synthetic-not-original.zip"
    file.write_bytes(b"NOT REAL GOLD SOURCE")
    plan=factory.make_plan(file,years=(2012,),
        source_sha256=factory.SOURCE_SHA,engine_commit="a"*40)
    assert plan["schema"]==factory.SCHEMA
    assert plan["source_sha256"]==factory.SOURCE_SHA
    assert plan["engine_commit"]=="a"*40
    assert plan["exposure_context"]=="historical_exposed"
    assert len(plan["grids"])==6
    assert factory.count_definitions(plan["grids"])==228
    # make_plan is a DEFINITION; only freeze_plan verifies source BYTES.
    with pytest.raises(ValueError):
        factory.make_plan(file,years=(2012,),source_sha256="b"*64,engine_commit="a"*40)
    with pytest.raises(ValueError):
        factory.make_plan(file,years=(2012,),source_sha256=factory.SOURCE_SHA,engine_commit="short")
    with pytest.raises(ValueError):
        factory.make_plan(Path("relative.zip"),years=(2012,),source_sha256=factory.SOURCE_SHA,engine_commit="a"*40)


def test_no_source_freeze_fails_without_publishing(tmp_path):
    with pytest.raises(ValueError):
        factory.make_plan(tmp_path/"absent.zip",years=(2012,),
             source_sha256=factory.SOURCE_SHA,engine_commit="a"*40)


def test_annual_zip_preflight_rejects_missing_and_duplicate_years(tmp_path):
    import zipfile
    source=tmp_path/"years.zip"
    with zipfile.ZipFile(source,"w") as z:
        z.writestr("2012.json","[]")
        z.writestr("2013.json","[]")
    factory.require_annual_source_members(source,(2012,2013))
    with pytest.raises(ValueError,match="missing"):
        factory.require_annual_source_members(source,(2012,2014))
    with zipfile.ZipFile(source,"a") as z:
        z.writestr("extra_2012.json","[]")
    with pytest.raises(ValueError,match="duplicates"):
        factory.require_annual_source_members(source,(2012,))


def test_non_zip_source_cannot_be_frozen(tmp_path):
    source=tmp_path/"notzip.zip"
    source.write_bytes(b"fake")
    with pytest.raises(ValueError,match="valid ZIP"):
        factory.require_annual_source_members(source,(2012,))


def test_freeze_plan_stops_future_year_and_existing_target(tmp_path, monkeypatch):
    import hashlib
    import sys
    import types
    import zipfile
    from datetime import date as Date

    source=tmp_path/"source.zip"
    with zipfile.ZipFile(source,"w") as z:
        z.writestr("2012.json","[]")
        z.writestr("2026.json","[]")
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(factory,"SOURCE_SHA",original)
    fake=types.ModuleType("research_batch_orchestrator")
    fake.file_sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    fake.checkout_commit=lambda:"a"*40
    fake.expand=lambda p:([None]*factory.count_definitions(p["grids"]),"f"*64)
    fake.atomic_manifest=lambda p,obj:p.write_text(json.dumps(obj))
    monkeypatch.setitem(sys.modules,"scripts.research_batch_orchestrator",fake)
    from scripts import generate_quant_research_grid as imported_factory
    monkeypatch.setattr(imported_factory,"SOURCE_SHA",original)

    class FrozenClock:
        @staticmethod
        def today():
            return Date(2026,10,29)
    monkeypatch.setattr(factory,"date",FrozenClock)
    dest=tmp_path/"frozen_plan.json"
    with pytest.raises(ValueError,match="Current or future"):
        factory.freeze_plan(source,dest,years=(2026,))
    assert not dest.exists()
    out=factory.freeze_plan(source,dest,years=(2012,))
    assert out["status"]=="FROZEN_DESIGN_ONLY_NO_BACKTEST"
    assert out["defined_jobs"]==228
    assert dest.exists()
    with pytest.raises(ValueError,match="Private plan output"):
        factory.freeze_plan(source,dest,years=(2012,))
