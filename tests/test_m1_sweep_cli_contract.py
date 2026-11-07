"""End-to-end M1 sweep CLI smoke on synthetic OHLC; not actual Gold source."""
import sys
import pandas as pd
import pytest
from norisk_quant import cli

BASE = ["norisk", "backtest", "--data", "/no-actual-gold.zip",
        "--start", "2024-01-01", "--end", "2024-01-01", "--out", "/ignored",
        "--strategy", "m1-sweep"]


@pytest.mark.parametrize("extra,error", [
    (["--timeframe", "M15"], "requires --timeframe M1"),
    (["--timeframe", "M1", "--sweep-lookback", "2"], "--sweep-lookback must be >=3"),
    (["--timeframe", "M1", "--all-in-cost-per-ounce", "0"], "exactly $0.40/oz"),
])
def test_reject_unsafe_cli_settings_before_market_io(monkeypatch,capsys,extra,error):
    monkeypatch.setattr(sys,"argv",BASE + extra)
    with pytest.raises(SystemExit) as caught:
        cli.main()
    assert caught.value.code==2
    assert error in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["fast", "reference"])
def test_cli_dispatches_real_sweep_and_fixed_fee(monkeypatch,mode):
    rows = [[100,101,99,100] for _ in range(3)] + [
      [100,100.2,98.2,99.4], [99.4,100.1,99.0,100], [100,104,99.8,103]]
    frame = pd.DataFrame(rows,columns=["o","h","l","c"],
        index=pd.date_range("2024-01-01",periods=len(rows),freq="min",tz="UTC"),dtype=float)
    monkeypatch.setattr(cli,"load_market",lambda *args:frame)
    monkeypatch.setattr(cli,"fingerprint_loaded_m1",lambda _:"a"*64)
    collected=[]
    def record(result,settings,out,**kwargs):
        collected.append((result,settings,kwargs))
        return {"status":"SYNTHETIC_ONLY"}
    monkeypatch.setattr(cli,"report",record)
    monkeypatch.setattr(sys,"argv",BASE + ["--timeframe","M1", "--sweep-lookback","3",
        "--sweep-min-excess-usd","0.2","--sweep-reclaim-usd","0.1",
        "--sweep-stop-buffer-usd","0.2", "--sweep-reward-risk","2",
        "--sweep-max-stop-usd","9", "--execution",mode])
    cli.main()
    assert len(collected)==1
    result,settings,kwargs=collected[0]
    assert len(result.trades)==1
    assert result.trades.iloc[0]["cost"]==pytest.approx(.4)
    assert settings.roundtrip_cost_per_ounce==.4
    assert kwargs["run_parameters"]["strategy"]=="m1-sweep"
    assert kwargs["run_parameters"]["execution"]==mode
