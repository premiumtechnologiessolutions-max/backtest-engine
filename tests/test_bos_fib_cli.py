"""End-to-end CLI smoke test using synthetic M1 source (no private gold data)."""
from __future__ import annotations

import json
import math
import sys

import pandas as pd

from norisk_quant.cli import main


def test_bos_fib_m1_cli_runs_and_writes_period_reports(tmp_path, monkeypatch, capsys):
    t = pd.date_range("2024-01-02T00:00Z", periods=320, freq="min")
    price = [100 + i * 0.075 + 1.7 * math.sin(i * 0.26) for i in range(len(t))]
    frame = pd.DataFrame({
        "ts": [int(x.timestamp()) for x in t],
        "o": price, "h": [p + 0.14 for p in price],
        "l": [p - 0.14 for p in price], "c": price,
        "ao": [p + 0.40 for p in price],
        "ah": [p + 0.54 for p in price],
        "al": [p + 0.26 for p in price],
        "ac": [p + 0.40 for p in price],
    })
    source = tmp_path / "synthetic_bidask_m1.csv"
    destination = tmp_path / "result"
    frame.to_csv(source, index=False)
    monkeypatch.setattr(sys, "argv", [
        "norisk", "backtest", "--data", str(source),
        "--start", "2024-01-02", "--end", "2024-01-02",
        "--strategy", "bos-fib", "--timeframe", "M1",
        "--bos-fib-entry", "0.618", "--bos-rr", "1",
        "--ounces", "1", "--all-in-cost-per-ounce", "0.40",
        "--out", str(destination),
    ])
    main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["engine"].startswith("noriskfx-quant-engine")
    assert summary["accounting_checks"] == "PASSED"
    assert (destination / "trades.csv").exists()
    assert (destination / "weekly.csv").exists()
    assert (destination / "monthly.csv").exists()
    assert (destination / "gap_catalogue.csv").exists()
    assert (destination / "summary.json").exists()
