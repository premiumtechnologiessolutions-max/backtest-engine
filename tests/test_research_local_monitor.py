"""Synthetic-only read-only localhost monitor tests, no raw source."""
from datetime import datetime, timezone
from http.client import HTTPConnection
import json
from threading import Thread
from urllib.request import urlopen
from urllib.error import HTTPError

import pytest

from scripts.research_local_monitor import (
    safe_status, make_handler, ThreadingHTTPServer,
)


def _status(root):
    data = {"schema": "NRFX_ARITHMETIC_CAMPAIGN_V1",
            "status": "RUNNING_OBSERVED",
            "started_utc": "2026-10-30T11:00:00+00:00",
            "updated_utc": "2026-10-30T11:00:00+00:00",
            "training_only": True, "independent_oos_proven": False,
            "live_trading_authorized": False,
            "completed": [{"generation": 1,
                          "status": "EXECUTED_AND_VERIFIED_FEEDBACK",
                          "input_sha256": "a" * 64}]}
    (root / "campaign_status.json").write_text(json.dumps(data))


def test_stale_monitor_does_not_claim_oos_or_publish_sha(tmp_path):
    _status(tmp_path)
    now = datetime(2026, 10, 30, 11, 11, tzinfo=timezone.utc)
    result = safe_status(tmp_path, current=now)
    assert result["observation_stale"] is True
    assert result["completed_generations"] == 1
    assert result["independent_oos_proven"] is False
    assert not any("sha" in k for k in result)


def test_reject_tampered_status_or_symlink(tmp_path):
    _status(tmp_path)
    path = tmp_path / "campaign_status.json"
    data = json.loads(path.read_text())
    data["independent_oos_proven"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="provenance"):
        safe_status(tmp_path)
    path.unlink()
    path.symlink_to(tmp_path / "hidden")
    with pytest.raises(ValueError, match="symlink"):
        safe_status(tmp_path)


def test_reject_future_or_non_utc_status_freshness(tmp_path):
    _status(tmp_path)
    path = tmp_path / "campaign_status.json"
    now = datetime(2026, 10, 30, 11, 0, tzinfo=timezone.utc)
    record = json.loads(path.read_text())
    record["updated_utc"] = "2026-10-30T11:05:00+00:00"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="future"):
        safe_status(tmp_path, current=now)
    record["updated_utc"] = "2026-10-30T12:00:00+01:00"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="UTC"):
        safe_status(tmp_path, current=now)
    record["updated_utc"] = "2026-10-30T11:00:30+00:00"
    path.write_text(json.dumps(record))
    assert safe_status(tmp_path, current=now)["seconds_since_update"] == 0


def test_http_only_exposes_allowlisted_readonly_paths(tmp_path, monkeypatch):
    from scripts import research_training_dashboard
    monkeypatch.setattr(research_training_dashboard, "read_evidence",
                        lambda root: [], raising=False)
    _status(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path))
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever,
                    kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(address + "/api/status", timeout=3) as response:
            assert json.load(response)["completed_generations"] == 1
            assert response.headers["Cache-Control"] == "no-store"
            assert "Content-Security-Policy" in response.headers
        with urlopen(address + "/", timeout=3) as response:
            assert b"Quant Research Control Plane" in response.read()
        with pytest.raises(HTTPError) as error:
            urlopen(address + "/Gold%20data.zip", timeout=3)
        assert error.value.code == 404

        def request_with_hosts(path, hosts):
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                conn.putrequest("GET", path, skip_host=True)
                for host in hosts:
                    conn.putheader("Host", host)
                conn.endheaders()
                response = conn.getresponse()
                return response.status, response.read()
            finally:
                conn.close()

        local = f"127.0.0.1:{server.server_port}"
        assert request_with_hosts("/api/status", [local])[0] == 200
        for path in ("/", "/api/status", "/api/generations"):
            for hosts in ([], ["attacker.example"], [f"attacker.example:{server.server_port}"],
                          [f"localhost:{server.server_port}"], ["127.0.0.1"],
                          [local, f"attacker.example:{server.server_port}"]):
                status, body = request_with_hosts(path, hosts)
                assert status == 403
                assert b"completed_generations" not in body
                assert b"Quant Research Control Plane" not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
