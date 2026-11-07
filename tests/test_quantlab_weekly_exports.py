"""SHA-locked owner-local weekly and evidence export contract.

Synthetic ledgers only. No real Gold source or source ZIP in this test.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

from scripts import quantlab_desktop as app


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    fake = tmp_path / "mock-gold.zip"
    fake.write_bytes(b"ONLY_TEST_BYTES")
    original_sha = app.lab.file_sha
    monkeypatch.setattr(app.lab, "file_sha",
                        lambda p: app.SOURCE_SHA if Path(p) == fake else original_sha(p))
    monkeypatch.setattr(app.lab, "checkout_commit", lambda: "a" * 40)
    hub = app.ResearchHub(tmp_path / "private")
    hub.configure(str(fake))
    ident = hub.freeze({
        "year": 2012, "strategy": "ema", "timeframe": "M15",
        "execution": "fast", "grid": {"fast": [8], "slow": [21]},
    })["plan_id"]
    jobs, _ = app.lab.expand(hub._plan(ident))
    job_id = jobs[0]["id"]
    run = hub._run_folder(ident)
    folder = run / "runs" / job_id
    folder.mkdir(parents=True)
    files = {
        "trades.csv": b"net_pnl,cost\n1,0.4\n",
        "weekly.csv": b"period,trades,net_pnl,total_cost\n2012-01-02/2012-01-08,1,1,0.4\n",
        "monthly.csv": b"period,trades,net_pnl,total_cost\n2012-01,1,1,0.4\n",
        "summary.json": b'{"test":"synthetic"}\n',
    }
    for name, data in files.items():
        (folder / name).write_bytes(data)
    record = {"status": app.lab.PASSED}
    for name, data in files.items():
        record[name.split(".")[0] + "_sha256"] = hashlib.sha256(data).hexdigest()
    app.put_once(run / "batch_manifest.json", {
        "schema": app.lab.SCHEMA, "plan_sha256": ident,
        "source_sha256": app.SOURCE_SHA,
        "engine_commit": "a" * 40,
        "results": {job_id: record},
    })
    return hub, ident, job_id, folder, files


def test_accepted_weekly_report_has_no_extra_fees(evidence):
    hub, ident, job, _, files = evidence
    rows = hub.weekly(ident, job)
    assert len(rows) == 1
    assert rows[0]["total_cost"] == .4
    assert rows[0]["net_pnl"] == 1
    for name, raw in files.items():
        payload, mime = hub.evidence_bytes(ident, job, name)
        assert payload == raw
        assert mime.startswith("application/json" if name.endswith(".json") else "text/csv")


@pytest.mark.parametrize("filename", [
    "../config.json", "/etc/passwd", "Gold data.zip", "equity_m1.csv",
])
def test_raw_zip_and_path_traversal_cannot_be_exported(evidence, filename):
    hub, ident, job, _, _ = evidence
    with pytest.raises(ValueError, match="Unsupported"):
        hub.evidence_bytes(ident, job, filename)


def test_tampered_report_never_downloads(evidence):
    hub, ident, job, folder, _ = evidence
    (folder / "weekly.csv").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        hub.weekly(ident, job)
    with pytest.raises(ValueError, match="integrity"):
        hub.evidence_bytes(ident, job, "weekly.csv")
