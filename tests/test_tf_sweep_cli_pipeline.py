"""M15/H1 sweep actual close-confirmed market signal CLI dispatch."""
import sys
import pandas as pd
import pytest
from norisk_quant import cli


def frame(timeframe):
    width={"M15":15,"H1":60}[timeframe]
    rows=[]
    for bar in range(14):
        o,h,l,c=(100.,101.,99.,100.) if bar!=12 else (100.,100.8,98.,99.5)
        rows.extend([[o,h,l,c]]*width)
    return pd.DataFrame(rows,columns=["o","h","l","c"],
        index=pd.date_range("2024-01-08T12:00:00Z",periods=len(rows),freq="min",tz="UTC"))


@pytest.mark.parametrize("tf", ["M15","H1"])
@pytest.mark.parametrize("mode",["reference","fast"])
def test_actual_multiframe_sweep_cli_no_lookahead(monkeypatch,tf,mode,capsys):
    data=frame(tf)
    monkeypatch.setattr(cli,"load_market",lambda *args: data)
    monkeypatch.setattr(cli,"fingerprint_loaded_m1",lambda _: "f"*64)
    results=[]
    def report_stub(result, settings, out, **kwargs):
        results.append((result,settings,kwargs))
        return {"status":"SYNTHETIC"}
    monkeypatch.setattr(cli,"report",report_stub)
    monkeypatch.setattr(sys,"argv",["norisk","backtest","--data","/fake.json",
        "--start","2024-01-08","--end","2024-01-08","--out","/unused",
        "--strategy","tf-sweep","--timeframe",tf,"--execution",mode])
    cli.main(); capsys.readouterr()
    assert len(results)==1
    result,settings,metadata=results[0]
    assert result.trades.shape[0]==1
    assert pd.Timestamp(result.trades.iloc[0]["signal_at"]) == data.index[13*({"M15":15,"H1":60}[tf])]
    assert settings.roundtrip_cost_per_ounce==.40
    assert metadata["run_parameters"]["strategy"]=="tf-sweep"


@pytest.mark.parametrize("args,message",[
    (["--timeframe","M1"],"requires --timeframe M15 or H1"),
    (["--timeframe","H4"],"requires --timeframe M15 or H1"),
    (["--timeframe","M15","--tf-sweep-lookback-bars","2"],"must be >=3"),
])
def test_tf_sweep_unsafe_args_before_market_io(monkeypatch,capsys,args,message):
    monkeypatch.setattr(sys,"argv",["norisk","backtest","--data","/missing",
      "--start","2024-01-08","--end","2024-01-08","--out","/unused",
      "--strategy","tf-sweep"]+args)
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code==2
    assert message in capsys.readouterr().err
