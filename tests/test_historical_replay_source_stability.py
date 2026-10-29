"""Synthetic source-mutation regression tests for both official replay entry points.

These tests do NOT use, recreate, or certify the private Gold data.zip.
The SHA checks are deliberately mocked to simulate a source changing while
an otherwise successful historical run is in progress.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pandas as pd
import pytest

import scripts.run_bos_fib_frozen_sensitivity as frozen
import scripts.verify_bos_h1_parity as parity


def _synthetic_zip(tmp_path: Path) -> Path:
    source = tmp_path / "SYNTHETIC_NOT_REAL_GOLD.zip"
    rows = []
    for month in range(1, 13):
        start = pd.Timestamp(year=2012, month=month, day=2, tz="UTC")
        for minute in range(8):
            stamp = start + pd.Timedelta(minutes=minute)
            rows.append({
                "ts": int(stamp.timestamp()),
                "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0,
                "ao": 100.4, "ah": 101.4, "al": 99.4, "ac": 100.4,
            })
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("2012.json", json.dumps(rows))
    return source


def test_frozen_annual_runner_rejects_source_mutation_before_combined_certification(
    tmp_path, monkeypatch
):
    source = _synthetic_zip(tmp_path)
    hashes = iter([frozen.SOURCE_SHA, "0" * 64])
    monkeypatch.setattr(frozen, "sha256_file", lambda _: next(hashes))
    destination = tmp_path / "reports"
    with pytest.raises(ValueError, match="changed during frozen replay"):
        frozen.execute(source, [2012], destination)
    # Annual diagnostics may exist; never publish a combined certification.
    assert (destination / "2012" / "summary.json").exists()
    assert not (destination / "frozen_sensitivity_summary.json").exists()


@pytest.mark.parametrize("source_mutated", [False, True])
def test_independent_13_field_replay_rechecks_archive_after_processing(
    tmp_path, monkeypatch, source_mutated
):
    checks = []
    def fake_sha(_):
        checks.append(True)
        if source_mutated and len(checks) == 2:
            return "0" * 64
        return parity.EXPECTED_MARKET_SHA256

    monkeypatch.setattr(parity, "file_sha256", fake_sha)
    yearly = pd.DataFrame([
        {"year": 2012, "variant": variant, "trades": 0,
         "orders": 0, "net_usd_oz": 0.0}
        for variant in ("h1_only", "h1_and_5x")
    ])
    def fake_reference(path, *, required_columns):
        if Path(path).name == "yearly.csv":
            return yearly
        return pd.DataFrame(columns=sorted(required_columns))

    monkeypatch.setattr(parity, "read_reference_csv", fake_reference)
    market = pd.DataFrame(
        {"o": [100.0] * 12, "h": [101.0] * 12,
         "l": [99.0] * 12, "c": [100.0] * 12},
        index=pd.date_range("2012-01-01T00:00:00Z", periods=12, freq="MS"),
    )
    monkeypatch.setattr(parity, "load_market", lambda *args, **kwargs: market)
    monkeypatch.setattr(parity, "bos_fib_limit_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(parity, "filter_orders_h1", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        parity, "run_limits",
        lambda *args, **kwargs: SimpleNamespace(
            trades=pd.DataFrame(columns=[
                "signal_at", "entry_at", "closed_at", "side", "entry_price",
                "exit_price", "stop", "target", "gross_pnl", "cost",
                "net_pnl", "exit_reason", "gap_minutes",
            ]),
            uncertain_entry_tp_deferred=0,
        ),
    )

    if source_mutated:
        with pytest.raises(ValueError, match="changed during historical replay"):
            parity.verify(tmp_path / "SYNTHETIC.zip", tmp_path, [2012])
    else:
        outcome = parity.verify(tmp_path / "SYNTHETIC.zip", tmp_path, [2012])
        assert outcome["status"] == "PASSED"
        assert outcome["scenarios_verified"] == 2
        assert outcome["trades_matched"] == 0
    assert len(checks) == 2
