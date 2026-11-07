"""Synthetic original-format Gold ZIP → read-only causal CLI tests."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts.research_gold_macro_context import read_local_context, main
from norisk_quant.openbb_fred_snapshot import freeze_fred_snapshot


def sample(tmp_path):
    archive = tmp_path / "private-gold.zip"
    candles = [
        {"ts": 1793800680, "o": 2000.0, "h": 2001.0, "l": 1999.0,
         "c": 2000.5, "ao": 2000.2, "ah": 2001.2,
         "al": 1999.2, "ac": 2000.7},
        {"ts": 1793800740, "o": 2001.0, "h": 2002.0, "l": 2000.0,
         "c": 2001.5, "ao": 2001.2, "ah": 2002.2,
         "al": 2000.2, "ac": 2001.7},
    ]
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Gold-2026.json", json.dumps(candles))
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_cli_reconciles_synthetic_gold_zip(tmp_path, capsys):
    archive, sha = sample(tmp_path)
    args = ["--gold-zip", str(archive), "--source-sha256", sha,
            "--start", "2026-11-04", "--end", "2026-11-04",
            "--decision-at", "2026-11-04T13:59:00Z"]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["source_zip_sha256"] == sha
    assert result["loaded_bars"] == 2
    assert result["context"]["last_gold_bid_close"] == 2000.5
    assert result["live_trading_authorized"] is False


def test_source_mismatch_refused(tmp_path):
    archive, sha = sample(tmp_path)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        read_local_context(
            archive, source_sha256="a" * 64,
            start="2026-11-04", end="2026-11-04",
            decision_at="2026-11-04T14:00:00Z")


def test_macro_snapshot_not_backdated(tmp_path):
    archive, sha = sample(tmp_path)
    snap = freeze_fred_snapshot(
        "GDP", "2024-01-01", "2024-12-31",
        [{"date": "2024-01-01", "GDP": 10.0}],
        captured_at="2026-11-04T14:00:00Z")
    p = tmp_path / "fred.json"
    p.write_text(json.dumps(snap), encoding="utf-8")
    old = read_local_context(
        archive, source_sha256=sha,
        start="2026-11-04", end="2026-11-04",
        decision_at="2026-11-04T13:59:00Z", fred_snapshot_path=p)
    assert old["context"]["fred_last_observed_value"] is None
    new = read_local_context(
        archive, source_sha256=sha,
        start="2026-11-04", end="2026-11-04",
        decision_at="2026-11-04T14:00:00Z", fred_snapshot_path=p)
    assert new["context"]["fred_last_observed_value"] == 10.0
    assert new["prospective_oos_proven"] is False


def test_duplicate_fred_keys_refused(tmp_path):
    archive, sha = sample(tmp_path)
    p = tmp_path / "fred.json"
    p.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        read_local_context(
            archive, source_sha256=sha,
            start="2026-11-04", end="2026-11-04",
            decision_at="2026-11-04T14:00:00Z", fred_snapshot_path=p)


def test_symlinked_gold_file_rejected(tmp_path):
    archive, sha = sample(tmp_path)
    linked = tmp_path / "link.zip"
    try:
        linked.symlink_to(archive)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError, match="private annual Gold ZIP"):
        read_local_context(
            linked, source_sha256=sha,
            start="2026-11-04", end="2026-11-04",
            decision_at="2026-11-04T14:00:00Z")
