"""Synthetic-only integration of frozen arithmetic formula with canonical CLI."""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
import pytest
from norisk_quant import cli
from norisk_quant.math_discovery import Formula


def args(path, *extra):
    return ["norisk", "backtest", "--data", "/unread/private/source", "--start", "2024-01-02",
            "--end", "2024-01-02", "--out", "/tmp/unused", "--strategy", "arithmetic",
            "--timeframe", "M1", "--formula-json", str(path), *extra]


def test_frozen_formula_executes_and_records_normalized_identity(tmp_path, monkeypatch):
    source = tmp_path / "frozen.json"
    source.write_text('{"lookback":10,"threshold":0.2,"cooldown":5}')
    rng = np.random.default_rng(17)
    o = 2000 + np.cumsum(rng.normal(0, 0.5, 180))
    c = o + rng.normal(0, 0.2, len(o))
    frame = pd.DataFrame({"o":o, "h":np.maximum(o,c)+0.3,
                          "l":np.minimum(o,c)-0.3, "c":c},
                         index=pd.date_range("2024-01-02",periods=len(o),freq="min",tz="UTC"))
    seen = {}
    monkeypatch.setattr(cli, "load_market", lambda *a: frame)
    monkeypatch.setattr(cli, "fingerprint_loaded_m1", lambda _: "synthetic-not-a-source-hash")
    def report_stub(result, settings, out, *, source, provenance, run_parameters):
        seen["params"] = run_parameters
        seen["trades"] = result.trades
        seen["settings"] = settings
        return {"synthetic_test": True}
    monkeypatch.setattr(cli, "report", report_stub)
    monkeypatch.setattr(sys, "argv", args(source, "--execution", "fast"))
    cli.main()
    expected = Formula(lookback=10,threshold=0.2,cooldown=5)
    assert seen["params"]["arithmetic_formula_sha256"] == expected.identity()
    assert seen["params"]["arithmetic_formula"]["lookback"] == 10
    assert seen["params"]["arithmetic_formula"]["reward_risk"] == 1.5
    assert seen["settings"].roundtrip_cost_per_ounce == 0.40
    assert seen["trades"] is not None


@pytest.mark.parametrize("contents", [
    '{"lookback":20,"lookback":10}',
    '{"threshold":NaN}',
    '{"threshold":Infinity}',
    '{"threshold":1e309}',
    '{"feature_a":true}',
    '{"unknown_setting":1}',
    '[]',
    '{broken json',
])
def test_malformed_formula_rejected_before_market_open(tmp_path, monkeypatch, contents):
    source=tmp_path / "formula.json"
    source.write_text(contents)
    monkeypatch.setattr(cli, "load_market", lambda *a: pytest.fail("opened market before formula validation"))
    monkeypatch.setattr(sys, "argv", args(source))
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("changes", [
    ["--timeframe", "H1"],
    ["--all-in-cost-per-ounce", "0"],
])
def test_invalid_execution_policy_fails_closed(tmp_path, monkeypatch, changes):
    source=tmp_path / "formula.json"
    source.write_text("{}")
    monkeypatch.setattr(cli, "load_market", lambda *a: pytest.fail("opened market before policy validation"))
    monkeypatch.setattr(sys, "argv", args(source, *changes))
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def test_formula_json_rejected_for_unrelated_strategy(tmp_path, monkeypatch):
    source=tmp_path / "formula.json"
    source.write_text("{}")
    command=args(source)
    command[command.index("arithmetic")] = "ema"
    monkeypatch.setattr(cli, "load_market", lambda *a: pytest.fail("opened market before policy validation"))
    monkeypatch.setattr(sys, "argv", command)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
