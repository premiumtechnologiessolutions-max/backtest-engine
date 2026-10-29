"""Every advertised Fibonacci research level must be executable by BOS config.

Frozen grid definitions are NOT historical market backtests.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest
from norisk_quant.bos_fib import BosFibSettings
from norisk_quant import cli
from scripts import generate_quant_research_grid as factory
from scripts import research_batch_orchestrator as batch

LEVELS = (.50, .62, .705, .79, .87)


def test_all_custom_fib_levels_have_valid_frozen_bos_execution_configs(tmp_path):
    source=tmp_path/"synthetic-not-real-gold.zip"
    source.write_bytes(b"DO NOT TREAT AS ORIGINAL MARKET DATA")
    plan=factory.make_plan(source,years=(2012,),source_sha256=factory.SOURCE_SHA,
                           engine_commit="a"*40)
    jobs,_ = batch.expand(plan)
    annual_bos=[job for job in jobs if job["spec"]["strategy"]=="bos-fib"]
    assert len(annual_bos)==40
    assert {item["spec"]["parameters"]["bos_fib_entry"] for item in annual_bos}==set(LEVELS)
    for job in annual_bos:
        cfg=BosFibSettings(
            pivot_left=job["spec"]["parameters"]["bos_pivot_left"],
            pivot_right=job["spec"]["parameters"]["bos_pivot_right"],
            fib_entry=job["spec"]["parameters"]["bos_fib_entry"],
            zone_lower=job["spec"]["parameters"]["bos_zone_lower"],
            zone_upper=job["spec"]["parameters"]["bos_zone_upper"],
            reward_risk=job["spec"]["parameters"]["bos_rr"],
            sl_buffer_usd=job["spec"]["parameters"]["bos_stop_buffer_usd"],
            expiry_minutes=job["spec"]["parameters"]["bos_expiry_minutes"],
        )
        assert cfg.zone_lower <= cfg.fib_entry <= cfg.zone_upper


def test_frozen_default_bos_zone_is_unchanged():
    cfg=BosFibSettings()
    assert (cfg.zone_lower,cfg.fib_entry,cfg.zone_upper)==(.618,.618,.786)


@pytest.mark.parametrize("fibo", LEVELS)
def test_explicit_zone_can_hold_all_requested_fib_levels(fibo):
    cfg=BosFibSettings(fib_entry=fibo,zone_lower=.50,zone_upper=.87)
    assert cfg.fib_entry==fibo


@pytest.mark.parametrize("parameters",[
    {"bos_fib_entry":.50},  # default baseline zone excludes .50
    {"bos_fib_entry":.87},  # default baseline zone excludes .87
    {"bos_zone_lower":.80,"bos_fib_entry":.50,"bos_zone_upper":.90},
    {"bos_zone_lower":.50,"bos_fib_entry":.87,"bos_zone_upper":.85},
    {"bos_zone_lower":.50,"bos_fib_entry":.95,"bos_zone_upper":1.0},
])
def test_factory_rejects_invalid_bos_zone(parameters):
    spec={"strategy":"bos-fib","timeframe":"M1","execution":"reference",
          "start":"2012-01-01","end":"2012-12-31","parameters":parameters}
    with pytest.raises(ValueError,match="zone"):
        batch.check_spec(spec)


@pytest.mark.parametrize("extra",[
    ["--bos-fib-entry","0.50"],
    ["--bos-fib-entry","0.87"],
    ["--bos-zone-lower","0.50","--bos-fib-entry","0.87","--bos-zone-upper","0.86"],
    ["--bos-zone-lower","0.50","--bos-fib-entry","0.87","--bos-zone-upper","1.0"],
])
def test_invalid_cli_zone_rejected_before_private_market_access(monkeypatch,capsys,extra):
    monkeypatch.setattr(sys,"argv",[
        "norisk","backtest","--data","/private/not-found.zip",
        "--start","2012-01-01","--end","2012-12-31",
        "--out","/unused","--strategy","bos-fib","--timeframe","M1",*extra,
    ])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code==2
    assert "zone-lower" in capsys.readouterr().err


@pytest.mark.parametrize("fibo",LEVELS)
def test_explicit_cli_zone_reaches_canonical_execution_settings(monkeypatch,capsys,fibo):
    cfgs=[]
    bars=pd.DataFrame({"o":[100.],"h":[101.],"l":[99.],"c":[100.]},
                      index=pd.date_range("2012-01-01",periods=1,freq="min",tz="UTC"))
    monkeypatch.setattr(cli,"load_market",lambda *args:bars)
    monkeypatch.setattr(cli,"fingerprint_loaded_m1",lambda *args:"a"*64)
    def capture_orders(frame,*,settings):
        cfgs.append(settings)
        return []
    monkeypatch.setattr(cli,"bos_fib_limit_orders",capture_orders)
    monkeypatch.setattr(cli,"run_limits",lambda *args: object())
    monkeypatch.setattr(cli,"report",lambda *args,**kwargs:{"status":"SETTINGS_ONLY_SYNTHETIC"})
    monkeypatch.setattr(sys,"argv",[
        "norisk","backtest","--data","/not-a-source",
        "--start","2012-01-01","--end","2012-12-31","--out","/no-output",
        "--strategy","bos-fib","--timeframe","M1",
        "--bos-zone-lower",".50","--bos-fib-entry",str(fibo),"--bos-zone-upper",".87",
    ])
    cli.main()
    assert len(cfgs)==1
    assert (cfgs[0].zone_lower,cfgs[0].fib_entry,cfgs[0].zone_upper)==(.50,fibo,.87)
