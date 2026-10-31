"""Actual CLI market loader -> signal -> both engines -> evidence reports.

Synthetic fabricated BID/ASK only. Never evidence of Gold historical profitability.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sys

import pandas as pd
import pytest

from norisk_quant.cli import main


def test_actual_synthetic_source_through_both_engines_and_reports(tmp_path, monkeypatch, capsys):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [[100, 101, 99, 100] for _ in range(3)] + [
        [100, 100.2, 98.2, 99.4],
        [99.4, 100.1, 99, 100],
        [100, 104, 99.8, 103],
        [103, 103.1, 102.9, 103],
    ]
    rows = []
    for i, (o, h, l, c) in enumerate(bars):
        rows.append({
            "ts": int((start + timedelta(minutes=i)).timestamp()),
            "o": o, "h": h, "l": l, "c": c,
            "ao": o + .25, "ah": h + .25, "al": l + .25, "ac": c + .25,
            "v": 1,
        })
    source = tmp_path / "synthetic_source.json"
    source.write_text(json.dumps(rows), encoding="utf-8")
    reports = []
    for mode in ("reference", "fast"):
        dest = tmp_path / mode
        monkeypatch.setattr(sys, "argv", [
            "norisk", "backtest", "--data", str(source),
            "--start", "2024-01-01", "--end", "2024-01-01",
            "--out", str(dest), "--strategy", "m1-sweep",
            "--timeframe", "M1", "--execution", mode,
            "--sweep-lookback", "3", "--sweep-min-excess-usd", "0.2",
            "--sweep-reclaim-usd", "0.1", "--sweep-stop-buffer-usd", "0.2",
            "--sweep-reward-risk", "2", "--sweep-max-stop-usd", "9",
            "--all-in-cost-per-ounce", "0.40", "--ounces", "1",
        ])
        main()
        capsys.readouterr()
        summary = json.loads((dest / "summary.json").read_text(encoding="utf-8"))
        trades = pd.read_csv(dest / "trades.csv")
        monthly = pd.read_csv(dest / "monthly.csv")
        weekly = pd.read_csv(dest / "weekly.csv")
        equity = pd.read_csv(dest / "equity_m1.csv")
        assert summary["execution"] == "synthetic_same_reference_bid_ohlc_fixed_all_in_fee"
        assert summary["settings"]["roundtrip_cost_per_ounce"] == .4
        assert summary["run_parameters"]["strategy"] == "m1-sweep"
        assert summary["run_parameters"]["execution"] == mode
        assert len(summary["source_fingerprints"]["loaded_m1_bidask_sha256"]) == 64
        assert summary["trades"] == 1
        assert summary["net_pnl"] == pytest.approx(2.4)
        assert len(trades) == 1
        assert trades.loc[0, "cost"] == pytest.approx(.4)
        assert trades.loc[0, "exit_reason"] == "target"
        assert trades.loc[0, "net_pnl"] == pytest.approx(2.4)
        assert monthly.loc[0, "net_pnl"] == pytest.approx(2.4)
        assert weekly.loc[0, "net_pnl"] == pytest.approx(2.4)
        reports.append((trades, monthly, weekly, equity))
    for left, right in zip(reports[0], reports[1]):
        pd.testing.assert_frame_equal(left, right)
