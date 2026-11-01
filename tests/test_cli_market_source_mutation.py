"""Synthetic source-mutation regression; actual CLI must fail closed.

A market archive may be overwritten or truncated *after* the quote loader
reads it but *before* the backtest finishes. A single late SHA is misleading.
"""
import hashlib
import sys

import numpy as np
import pandas as pd
import pytest

from norisk_quant import cli


def market_frame():
    rng = np.random.default_rng(101)
    o = 2000 + np.cumsum(rng.normal(0, 0.4, 180))
    c = o + rng.normal(0, 0.1, len(o))
    return pd.DataFrame(
        {"o":o, "h":np.maximum(o,c)+.4,
         "l":np.minimum(o,c)-.4, "c":c},
        index=pd.date_range("2024-01-02", periods=len(o),freq="min",tz="UTC"))


def command(source, formula):
    return ["norisk", "backtest", "--data", str(source),
            "--start", "2024-01-02", "--end", "2024-01-02",
            "--out", "/tmp/synthetic-no-output", "--strategy", "arithmetic",
            "--timeframe", "M1", "--formula-json", str(formula),
            "--execution", "fast", "--all-in-cost-per-ounce", "0.40"]


def test_archive_changed_after_loading_never_publishes_summary(tmp_path,monkeypatch):
    archive = tmp_path / "fake_source.zip"
    archive.write_bytes(b"initial fake archive bytes")
    formula = tmp_path / "formula.json"
    formula.write_text("{}")
    frame = market_frame()
    def load_and_mutate(*args):
        archive.write_bytes(b"truncated different bytes")
        return frame
    monkeypatch.setattr(cli, "load_market", load_and_mutate)
    monkeypatch.setattr(cli, "fingerprint_loaded_m1", lambda _: "synthetic")
    monkeypatch.setattr(cli, "report", lambda *a, **kw: pytest.fail("published unsafe provenance"))
    monkeypatch.setattr(sys, "argv", command(archive, formula))
    with pytest.raises(ValueError, match="source file changed during backtest"):
        cli.main()


def test_stable_archive_keeps_exact_source_hash(tmp_path,monkeypatch):
    archive = tmp_path / "fake_source.zip"
    archive.write_bytes(b"stable fake archive bytes")
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    formula = tmp_path / "formula.json"
    formula.write_text("{}")
    monkeypatch.setattr(cli, "load_market", lambda *a: market_frame())
    monkeypatch.setattr(cli, "fingerprint_loaded_m1", lambda _: "synthetic")
    seen = {}
    def report_stub(result, settings, output, *, source, provenance,
                    run_parameters):
        seen.update(provenance)
        return {"synthetic_test":True}
    monkeypatch.setattr(cli, "report", report_stub)
    monkeypatch.setattr(sys, "argv", command(archive, formula))
    cli.main()
    assert seen["source_file_sha256"] == expected
