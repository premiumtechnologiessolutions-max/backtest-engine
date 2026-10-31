"""Real source parser and reports for M15/H1 research, using invented quotes only."""
from datetime import datetime, timedelta, timezone
import json
import sys

import pandas as pd
import pytest
from norisk_quant.cli import main


@pytest.mark.parametrize("tf,width", [("M15", 15), ("H1", 60)])
def test_tf_sweep_full_synthetic_bidask_source_and_engine_parity(tf, width, tmp_path, monkeypatch, capsys):
    start=datetime(2024,1,8,12,0,tzinfo=timezone.utc)
    rows=[]
    for j in range(14):
        o,h,l,c=(100.,101.,99.,100.) if j!=12 else (100.,100.8,98.,99.5)
        for k in range(width):
            rows.append({
                "ts":int((start+timedelta(minutes=j*width+k)).timestamp()),
                "o":o,"h":h,"l":l,"c":c,
                "ao":o+.25,"ah":h+.25,"al":l+.25,"ac":c+.25,"v":1,
            })
    path=tmp_path/"invented_quotes.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    outputs=[]
    for engine in ("reference","fast"):
        out=tmp_path/engine
        monkeypatch.setattr(sys,"argv",[
            "norisk","backtest","--data",str(path),
            "--start","2024-01-08","--end",("2024-01-09" if tf=="H1" else "2024-01-08"),
            "--out",str(out),"--strategy","tf-sweep",
            "--timeframe",tf,"--execution",engine,
            "--tf-sweep-lookback-bars","12",
            "--all-in-cost-per-ounce","0.40",
        ])
        main(); capsys.readouterr()
        summary=json.loads((out/"summary.json").read_text(encoding="utf-8"))
        trades=pd.read_csv(out/"trades.csv")
        assert summary["trades"]==1
        assert summary["settings"]["roundtrip_cost_per_ounce"]==.4
        assert trades.loc[0,"cost"]==pytest.approx(.4)
        assert trades.loc[0,"signal_at"]==pd.Timestamp(start+timedelta(minutes=13*width)).isoformat(sep=" ")
        assert summary["source_fingerprints"]["loaded_m1_rows"]==len(rows)
        outputs.append([pd.read_csv(out/x) for x in ("trades.csv","monthly.csv","weekly.csv","equity_m1.csv")])
    for ref,fast in zip(outputs[0],outputs[1]):
        pd.testing.assert_frame_equal(ref,fast)
